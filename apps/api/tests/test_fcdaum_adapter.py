from datetime import UTC, date, datetime

import pytest

from monitoring_api.adapters.base import MonitoringStatus
from monitoring_api.adapters.fcdaum import (
    FCDAUM_ATTEMPTS_SQL,
    FCDAUM_FRESHNESS_SQL,
    FCDAUM_LATEST_SQL,
    FcDaumAdapter,
)
from monitoring_api.db import ReadOnlyRepository, ensure_read_only_connection_string


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


def test_conflicting_application_intent_is_rejected() -> None:
    with pytest.raises(ValueError, match="ReadOnly"):
        ensure_read_only_connection_string(
            "Driver={ODBC Driver 18 for SQL Server};ApplicationIntent=ReadWrite"
        )
