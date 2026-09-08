from datetime import UTC, date, datetime

import pytest

from monitoring_api.adapters.base import MonitoringStatus
from monitoring_api.adapters.fcdaum import (
    FCDAUM_ATTEMPTS_SQL,
    FCDAUM_ATTEMPTS_FOR_RUNS_SQL,
    FCDAUM_COUNT_SQL,
    FCDAUM_FRESHNESS_SQL,
    FCDAUM_LATEST_SQL,
    FCDAUM_LIST_SQL,
    FCDAUM_RUN_SQL,
    FcDaumAdapter,
)
from monitoring_api.db import ReadOnlyRepository, ensure_read_only_connection_string
from monitoring_api.services.monitoring import MonitoringService


class FixtureRepository:
    def __init__(self, rows_by_sql: dict[str, list[dict[str, object]]]) -> None:
        self.rows_by_sql = rows_by_sql
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(
        self, sql: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        self.calls.append((sql, parameters))
        return self.rows_by_sql.get(sql, [])

    def ping(self) -> bool:
        return True


def _run_row() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "scheduled_date": date(2026, 9, 8),
        "started_at": datetime(2026, 9, 8, 1),
        "completed_at": datetime(2026, 9, 8, 1, 5),
        "raw_status": "SUCCESS",
        # 어댑터는 실행 행의 사전 집계가 아니라 최종 시도로 다시 계산해야 한다.
        "successful_units": 0,
        "failed_units": 1,
    }


def _attempt(
    attempt_no: int,
    raw_status: str,
    *,
    source_count: int,
    inserted_count: int,
    committed: bool,
) -> dict[str, object]:
    return {
        "unit_id": "hanchon",
        "unit_name": "한촌설렁탕",
        "attempt_no": attempt_no,
        "started_at": datetime(2026, 9, 8, 1, attempt_no),
        "completed_at": datetime(2026, 9, 8, 1, attempt_no, 30),
        "raw_status": raw_status,
        "source_count": source_count,
        "inserted_count": inserted_count,
        "changed_count": 0,
        "unchanged_count": 0,
        "committed": committed,
        "error_category": "API" if not committed else None,
    }


def test_fcdaum_retry_success_is_warning_and_all_attempts_are_preserved() -> None:
    repository = FixtureRepository(
        {
            FCDAUM_LATEST_SQL: [_run_row()],
            FCDAUM_ATTEMPTS_SQL: [
                _attempt(1, "FAILED_API", source_count=100, inserted_count=0, committed=False),
                _attempt(2, "SUCCESS", source_count=3, inserted_count=2, committed=True),
            ],
        }
    )

    run = FcDaumAdapter(repository).latest()

    assert run is not None
    assert run.status is MonitoringStatus.WARNING
    assert run.source_count == 3
    assert run.inserted_count == 2
    assert (run.successful_units, run.failed_units) == (1, 0)
    assert [attempt.attempt_no for attempt in run.attempts] == [1, 2]
    assert repository.calls[-1] == (FCDAUM_ATTEMPTS_SQL, ("run-1",))


def test_fcdaum_freshness_uses_only_the_three_fixed_business_tables() -> None:
    timestamp = datetime(2026, 9, 8, 2)
    repository = FixtureRepository(
        {
            FCDAUM_FRESHNESS_SQL: [
                {"dataset_id": "reports", "latest_at": timestamp},
                {"dataset_id": "issues", "latest_at": None},
                {"dataset_id": "missions", "latest_at": timestamp},
            ]
        }
    )

    result = FcDaumAdapter(repository).freshness()

    assert [item.dataset_id for item in result] == ["reports", "issues", "missions"]
    assert result[0].latest_at == timestamp.replace(tzinfo=UTC)
    assert "dbo.fc_daum_qsc_report" in FCDAUM_FRESHNESS_SQL
    assert "dbo.fc_daum_qsc_report_issue" in FCDAUM_FRESHNESS_SQL
    assert "dbo.fc_daum_mission" in FCDAUM_FRESHNESS_SQL


def test_fcdaum_count_runs_uses_fixed_query_and_utc_parameters() -> None:
    sql = FCDAUM_COUNT_SQL
    repository = FixtureRepository({sql: [{"total": 7}]})
    started_from = datetime(2026, 9, 1, tzinfo=UTC)
    started_to = datetime(2026, 9, 8, tzinfo=UTC)

    total = FcDaumAdapter(repository).count_runs(
        started_from=started_from,
        started_to=started_to,
        status=MonitoringStatus.WARNING,
    )

    assert total == 7
    assert repository.calls == [
        (
            sql,
            (
                datetime(2026, 9, 1),
                datetime(2026, 9, 1),
                datetime(2026, 9, 8),
                datetime(2026, 9, 8),
                "WARNING",
                "WARNING",
            ),
        )
    ]
    assert "AND (? IS NULL OR CASE" in FCDAUM_COUNT_SQL
    assert "dbo.FC_DAUM_COLLECTION_ATTEMPT" in FCDAUM_COUNT_SQL
    assert "AttemptNo" in FCDAUM_COUNT_SQL


def test_fcdaum_list_runs_filters_canonical_status_before_offset() -> None:
    repository = FixtureRepository({FCDAUM_LIST_SQL: []})

    FcDaumAdapter(repository).list_runs(
        status=MonitoringStatus.PARTIAL_FAILED,
        offset=20,
        limit=20,
    )

    assert repository.calls == [
        (
            FCDAUM_LIST_SQL,
            (None, None, None, None, "PARTIAL_FAILED", "PARTIAL_FAILED", 20, 20),
        )
    ]
    assert FCDAUM_LIST_SQL.index("AND (? IS NULL OR CASE") < FCDAUM_LIST_SQL.index(
        "OFFSET ? ROWS"
    )


def test_read_only_connection_and_repository_reject_write_statements() -> None:
    connection_string = ensure_read_only_connection_string(
        "Driver={ODBC Driver 18 for SQL Server};Server=db;Database=monitoring"
    )

    assert "ApplicationIntent=ReadOnly" in connection_string
    assert connection_string.count("ApplicationIntent=") == 1

    repository = ReadOnlyRepository(connection_string, connector=lambda _: None)
    with pytest.raises(ValueError, match="SELECT"):
        repository.fetch_all("DELETE FROM dbo.FC_DAUM_COLLECTION_RUN")
    with pytest.raises(ValueError, match="SELECT"):
        repository.fetch_all("SELECT * INTO dbo.audit_copy FROM dbo.FC_DAUM_COLLECTION_RUN")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 SELECT 2",
        "SELECT 1 GRANT SELECT TO monitor_user",
        "SELECT 1 REVOKE SELECT FROM monitor_user",
        "SELECT 1 DENY SELECT TO monitor_user",
        "SELECT 1 DBCC CHECKDB",
        "SELECT 1 BACKUP DATABASE monitoring TO DISK = 'backup.bak'",
        "SELECT 1 RESTORE DATABASE monitoring FROM DISK = 'backup.bak'",
        "SELECT 1 USE master",
        "SELECT NEXT VALUE FOR dbo.monitoring_sequence",
        "SELECT 1 RECEIVE TOP (1) * FROM dbo.message_queue",
        "SELECT 1 SEND ON CONVERSATION @handle MESSAGE TYPE [event] ('payload')",
        "SELECT 1 WRITETEXT dbo.documents.body @pointer 'payload'",
        "SELECT 1 UPDATETEXT dbo.documents.body @pointer 0 0 'payload'",
        "SELECT 1 -- 첫 문장\rRECEIVE TOP (1) * FROM dbo.message_queue",
        "SELECT '닫히지 않은 문자열",
    ],
)
def test_read_only_repository_rejects_semicolonless_batches_and_admin_commands(
    sql: str,
) -> None:
    connector_calls: list[str] = []
    repository = ReadOnlyRepository(
        "Driver={ODBC Driver 18 for SQL Server};Server=db",
        connector=lambda connection_string: connector_calls.append(connection_string),
    )

    with pytest.raises(ValueError, match="SELECT"):
        repository.fetch_all(sql)

    assert connector_calls == []


def test_connection_string_parser_preserves_braced_semicolon_values() -> None:
    result = ensure_read_only_connection_string(
        "Driver={ODBC Driver 18 for SQL Server};PWD={a;b};Server=db"
    )

    assert result == (
        "Driver={ODBC Driver 18 for SQL Server};PWD={a;b};Server=db;"
        "ApplicationIntent=ReadOnly"
    )


def test_connection_is_closed_when_cursor_creation_or_cursor_close_fails() -> None:
    class CloseFailingCursor:
        description = [("ready",)]

        def execute(self, _: str) -> None:
            return None

        def fetchall(self) -> list[tuple[int]]:
            return [(1,)]

        def close(self) -> None:
            raise RuntimeError("cursor close failed")

    class Connection:
        def __init__(self, *, cursor_fails: bool) -> None:
            self.cursor_fails = cursor_fails
            self.closed = False

        def cursor(self) -> CloseFailingCursor:
            if self.cursor_fails:
                raise RuntimeError("cursor creation failed")
            return CloseFailingCursor()

        def close(self) -> None:
            self.closed = True

    for cursor_fails in (True, False):
        connection = Connection(cursor_fails=cursor_fails)
        repository = ReadOnlyRepository(
            "Driver={ODBC Driver 18 for SQL Server};Server=db",
            connector=lambda _: connection,
        )

        with pytest.raises(RuntimeError, match="cursor"):
            repository.fetch_all("SELECT 1 AS ready")

        assert connection.closed is True


def test_conflicting_application_intent_is_rejected() -> None:
    with pytest.raises(ValueError, match="ReadOnly"):
        ensure_read_only_connection_string(
            "Driver={ODBC Driver 18 for SQL Server};ApplicationIntent=ReadWrite"
        )


def test_fcdaum_list_runs_loads_all_attempts_in_one_bulk_query() -> None:
    first = _run_row()
    second = {**_run_row(), "run_id": "run-2"}
    repository = FixtureRepository(
        {
            FCDAUM_LIST_SQL: [first, second],
            FCDAUM_ATTEMPTS_FOR_RUNS_SQL: [
                {
                    **_attempt(
                        1,
                        "SUCCESS",
                        source_count=1,
                        inserted_count=1,
                        committed=True,
                    ),
                    "run_id": "run-1",
                },
                {
                    **_attempt(
                        1,
                        "SUCCESS_EMPTY",
                        source_count=0,
                        inserted_count=0,
                        committed=True,
                    ),
                    "run_id": "run-2",
                },
            ],
        }
    )

    runs = FcDaumAdapter(repository).list_runs(limit=2)

    assert [run.run_id for run in runs] == ["run-1", "run-2"]
    assert [len(run.attempts) for run in runs] == [1, 1]
    assert [call[0] for call in repository.calls] == [
        FCDAUM_LIST_SQL,
        FCDAUM_ATTEMPTS_FOR_RUNS_SQL,
    ]
    assert repository.calls[1][1] == ('["run-1", "run-2"]',)


def test_all_fcdaum_fixed_queries_pass_the_read_only_validator() -> None:
    for sql in (
        FCDAUM_LATEST_SQL,
        FCDAUM_LIST_SQL,
        FCDAUM_COUNT_SQL,
        FCDAUM_RUN_SQL,
        FCDAUM_ATTEMPTS_SQL,
        FCDAUM_ATTEMPTS_FOR_RUNS_SQL,
        FCDAUM_FRESHNESS_SQL,
    ):
        ReadOnlyRepository._validate_select(sql)


def test_fcdaum_run_queries_have_a_total_candidate_order() -> None:
    order = "ORDER BY StartedAt DESC, CONVERT(char(36), RunId) DESC"
    assert order in FCDAUM_LATEST_SQL
    assert order in FCDAUM_LIST_SQL


def test_fcdaum_uuid_candidate_boundary_uses_service_string_order() -> None:
    """동일 StartedAt 후보는 서비스의 UUID 문자열 순서와 같아야 한다."""

    # SQL Server uniqueidentifier의 기본 역순은 끝 여섯 바이트가 우선하므로,
    # UUID 문자열 역순과 다르다. 전체 네 건 중 offset + limit 후보는 세 건이다.
    native_order = [
        "4aaaaaaa-bbbb-cccc-dddd-4eeeeeeeeeee",
        "1aaaaaaa-bbbb-cccc-dddd-3eeeeeeeeeee",
        "3aaaaaaa-bbbb-cccc-dddd-2eeeeeeeeeee",
        "2aaaaaaa-bbbb-cccc-dddd-1eeeeeeeeeee",
    ]
    string_order = [
        "4aaaaaaa-bbbb-cccc-dddd-4eeeeeeeeeee",
        "3aaaaaaa-bbbb-cccc-dddd-2eeeeeeeeeee",
        "2aaaaaaa-bbbb-cccc-dddd-1eeeeeeeeeee",
        "1aaaaaaa-bbbb-cccc-dddd-3eeeeeeeeeee",
    ]
    tied_at = datetime(2026, 9, 8, 1)
    rows_by_run_id = {
        run_id: {
            "run_id": run_id,
            "scheduled_date": date(2026, 9, 8),
            "started_at": tied_at,
            "completed_at": datetime(2026, 9, 8, 1, 1),
            "raw_status": "SUCCESS",
            "successful_units": 1,
            "failed_units": 0,
        }
        for run_id in native_order
    }

    class SqlServerGuidOrderingRepository:
        def fetch_all(
            self, sql: str, parameters: tuple[object, ...] = ()
        ) -> list[dict[str, object]]:
            if sql == FCDAUM_COUNT_SQL:
                return [{"total": len(rows_by_run_id)}]
            if sql == FCDAUM_LIST_SQL:
                offset, limit = parameters[-2:]
                ordered_ids = (
                    string_order
                    if "CONVERT(char(36), RunId) DESC" in sql
                    else native_order
                )
                return [
                    rows_by_run_id[run_id]
                    for run_id in ordered_ids[int(offset) : int(offset) + int(limit)]
                ]
            return []

        def ping(self) -> bool:
            return True

    result = MonitoringService([FcDaumAdapter(SqlServerGuidOrderingRepository())]).list_runs(
        offset=1,
        limit=2,
    )

    assert native_order != string_order
    assert result.total == 4
    assert [run.run_id for run in result.items] == string_order[1:3]


def test_read_only_validator_allows_a_single_tsql_cte_query() -> None:
    ReadOnlyRepository._validate_select(
        "WITH latest AS (SELECT MAX(StartedAt) AS started_at "
        "FROM dbo.FC_DAUM_COLLECTION_RUN) "
        "SELECT started_at FROM latest"
    )
