from datetime import UTC, date, datetime

import pytest

from monitoring_api.adapters.base import (
    CollectorAttempt,
    MonitoringStatus,
    derive_run_status,
)
from monitoring_api.adapters.hmr import (
    HMR_ATTEMPTS_SQL,
    HMR_FRESHNESS_SQL,
    HMR_LATEST_SQL,
    HMR_LIST_SQL,
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
        started_at=datetime(2026, 9, 8, 1),
        completed_at=datetime(2026, 9, 8, 1, 1),
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
