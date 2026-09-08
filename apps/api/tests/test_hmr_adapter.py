from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from monitoring_api.adapters.base import (
    CollectorAttempt,
    CollectorRun,
    FreshnessRecord,
    MonitoringStatus,
    derive_run_status,
)
from monitoring_api.adapters.hmr import (
    HMR_ATTEMPTS_SQL,
    HMR_ATTEMPTS_FOR_RUNS_SQL,
    HMR_COUNT_SQL,
    HMR_FRESHNESS_SQL,
    HMR_LATEST_SQL,
    HMR_LIST_SQL,
    HMR_RUN_SQL,
    HmrAdapter,
)


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


def test_hmr_partial_status_maps_to_partial_failed() -> None:
    repository = FixtureRepository(
        {
            HMR_LATEST_SQL: [
                {
                    "run_id": "run-2",
                    "scheduled_date": date(2026, 9, 8),
                    "started_at": datetime(2026, 9, 8, 5),
                    "completed_at": datetime(2026, 9, 8, 5, 3),
                    "raw_status": "PARTIAL",
                    "successful_units": 1,
                    "failed_units": 1,
                }
            ],
            HMR_ATTEMPTS_SQL: [],
        }
    )

    run = HmrAdapter(repository).latest()

    assert run is not None
    assert run.status is MonitoringStatus.PARTIAL_FAILED


def _attempt(unit_id: str, status: str, source_count: int = 1) -> CollectorAttempt:
    return CollectorAttempt(
        unit_id=unit_id,
        unit_name=unit_id,
        attempt_no=1,
        started_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
        completed_at=datetime(2026, 9, 8, 1, 1, tzinfo=UTC),
        raw_status=status,
        source_count=source_count,
        inserted_count=source_count,
        changed_count=0,
        unchanged_count=0,
        committed=status.startswith("SUCCESS"),
    )


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [
        ([_attempt("a", "SUCCESS"), _attempt("b", "FAILED_API")], MonitoringStatus.PARTIAL_FAILED),
        ([_attempt("a", "FAILED_API"), _attempt("b", "FAILED_DB")], MonitoringStatus.FAILED),
        (
            [_attempt("a", "SUCCESS_EMPTY", 0), _attempt("b", "SUCCESS_EMPTY", 0)],
            MonitoringStatus.SUCCESS_EMPTY,
        ),
    ],
)
def test_final_attempt_status_aggregation(
    attempts: list[CollectorAttempt], expected: MonitoringStatus
) -> None:
    assert derive_run_status(attempts, raw_status="SUCCESS") is expected


def test_hmr_queries_use_fixed_audit_and_order_table_identifiers() -> None:
    assert "dbo.CHANNEL_COLLECTION_RUN" in HMR_LATEST_SQL
    assert "dbo.CHANNEL_COLLECTION_ATTEMPT" in HMR_ATTEMPTS_SQL
    assert HMR_FRESHNESS_SQL.count("_ORDER_ITEM") == 8
    assert all(
        sql.lstrip().upper().startswith("SELECT")
        for sql in (HMR_LATEST_SQL, HMR_ATTEMPTS_SQL, HMR_FRESHNESS_SQL)
    )


def test_list_runs_converts_public_utc_filters_to_sql_datetime2_parameters() -> None:
    repository = FixtureRepository({HMR_LIST_SQL: []})
    started_from = datetime(2026, 9, 1, tzinfo=UTC)
    started_to = datetime(2026, 9, 8, tzinfo=UTC)

    HmrAdapter(repository).list_runs(
        started_from=started_from,
        started_to=started_to,
        offset=10,
        limit=25,
    )

    assert repository.calls == [
        (
            HMR_LIST_SQL,
            (
                datetime(2026, 9, 1),
                datetime(2026, 9, 1),
                datetime(2026, 9, 8),
                datetime(2026, 9, 8),
                10,
                25,
            ),
        )
    ]


def test_hmr_count_runs_uses_fixed_query_and_utc_parameters() -> None:
    sql = HMR_COUNT_SQL
    repository = FixtureRepository({sql: [{"total": 11}]})
    started_from = datetime(2026, 9, 1, tzinfo=UTC)
    started_to = datetime(2026, 9, 8, tzinfo=UTC)

    total = HmrAdapter(repository).count_runs(
        started_from=started_from, started_to=started_to
    )

    assert total == 11
    assert repository.calls == [
        (
            sql,
            (
                datetime(2026, 9, 1),
                datetime(2026, 9, 1),
                datetime(2026, 9, 8),
                datetime(2026, 9, 8),
            ),
        )
    ]


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 9, 8, 1),
        datetime(2026, 9, 8, 10, tzinfo=timezone(timedelta(hours=9))),
    ],
)
def test_common_models_reject_naive_and_non_utc_timestamps(timestamp: datetime) -> None:
    with pytest.raises(ValueError, match="UTC"):
        CollectorAttempt(
            unit_id="naver",
            unit_name="네이버",
            attempt_no=1,
            started_at=timestamp,
            completed_at=None,
            raw_status="SUCCESS",
            source_count=1,
            inserted_count=1,
            changed_count=0,
            unchanged_count=0,
            committed=True,
        )
    with pytest.raises(ValueError, match="UTC"):
        CollectorRun(
            collector_id="hmr",
            run_id="run-utc",
            scheduled_date=date(2026, 9, 8),
            started_at=timestamp,
            completed_at=None,
            status=MonitoringStatus.RUNNING,
            successful_units=0,
            failed_units=0,
            source_count=0,
            inserted_count=0,
            changed_count=0,
            unchanged_count=0,
        )
    with pytest.raises(ValueError, match="UTC"):
        FreshnessRecord(
            collector_id="hmr",
            dataset_id="naver",
            latest_at=timestamp,
        )
    with pytest.raises(ValueError, match="UTC"):
        CollectorAttempt(
            unit_id="naver",
            unit_name="네이버",
            attempt_no=1,
            started_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
            completed_at=timestamp,
            raw_status="SUCCESS",
            source_count=1,
            inserted_count=1,
            changed_count=0,
            unchanged_count=0,
            committed=True,
        )
    with pytest.raises(ValueError, match="UTC"):
        CollectorRun(
            collector_id="hmr",
            run_id="run-utc",
            scheduled_date=date(2026, 9, 8),
            started_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
            completed_at=timestamp,
            status=MonitoringStatus.SUCCESS,
            successful_units=1,
            failed_units=0,
            source_count=1,
            inserted_count=1,
            changed_count=0,
            unchanged_count=0,
        )


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 9, 8, 1),
        datetime(2026, 9, 8, 10, tzinfo=timezone(timedelta(hours=9))),
    ],
)
def test_list_runs_rejects_naive_and_non_utc_filters(timestamp: datetime) -> None:
    for filter_name in ("started_from", "started_to"):
        repository = FixtureRepository({HMR_LIST_SQL: []})

        with pytest.raises(ValueError, match="UTC"):
            HmrAdapter(repository).list_runs(**{filter_name: timestamp})

        assert repository.calls == []


def test_hmr_list_runs_loads_all_attempts_in_one_bulk_query() -> None:
    run_rows = [
        {
            "run_id": run_id,
            "scheduled_date": date(2026, 9, 8),
            "started_at": datetime(2026, 9, 8, 5),
            "completed_at": datetime(2026, 9, 8, 5, 3),
            "raw_status": "SUCCESS",
            "successful_units": 1,
            "failed_units": 0,
        }
        for run_id in ("run-1", "run-2")
    ]
    attempt_rows = [
        {
            "run_id": run_id,
            "unit_id": "naver",
            "unit_name": "naver",
            "attempt_no": 1,
            "started_at": datetime(2026, 9, 8, 5),
            "completed_at": datetime(2026, 9, 8, 5, 1),
            "raw_status": "SUCCESS",
            "source_count": 1,
            "inserted_count": 1,
            "changed_count": 0,
            "unchanged_count": 0,
            "committed": True,
            "error_category": None,
        }
        for run_id in ("run-1", "run-2")
    ]
    repository = FixtureRepository(
        {
            HMR_LIST_SQL: run_rows,
            HMR_ATTEMPTS_FOR_RUNS_SQL: attempt_rows,
        }
    )

    runs = HmrAdapter(repository).list_runs(limit=2)

    assert [run.run_id for run in runs] == ["run-1", "run-2"]
    assert [len(run.attempts) for run in runs] == [1, 1]
    assert [call[0] for call in repository.calls] == [
        HMR_LIST_SQL,
        HMR_ATTEMPTS_FOR_RUNS_SQL,
    ]
    assert repository.calls[1][1] == ('["run-1", "run-2"]',)


def test_all_hmr_fixed_queries_pass_the_read_only_validator() -> None:
    from monitoring_api.db import ReadOnlyRepository

    for sql in (
        HMR_LATEST_SQL,
        HMR_LIST_SQL,
        HMR_COUNT_SQL,
        HMR_RUN_SQL,
        HMR_ATTEMPTS_SQL,
        HMR_ATTEMPTS_FOR_RUNS_SQL,
        HMR_FRESHNESS_SQL,
    ):
        ReadOnlyRepository._validate_select(sql)


def test_hmr_run_queries_have_a_total_candidate_order() -> None:
    assert "ORDER BY StartedAt DESC, RunId DESC" in HMR_LATEST_SQL
    assert "ORDER BY StartedAt DESC, RunId DESC" in HMR_LIST_SQL
