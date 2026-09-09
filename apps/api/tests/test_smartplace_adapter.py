from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from monitoring_api.adapters.smartplace import (
    SMARTPLACE_ATTEMPTS_FOR_RUNS_SQL,
    SMARTPLACE_ATTEMPTS_SQL,
    SMARTPLACE_LATEST_SUCCESS_SQL,
    SMARTPLACE_LIST_SQL,
    SMARTPLACE_PRESENT_SCOPES_SQL,
    SMARTPLACE_RUN_SQL,
    ExpectedScope,
    SmartPlaceAdapter,
    SmartPlacePolicy,
)
from monitoring_api.db import ReadOnlyRepository
from monitoring_api.models import MonitoringStatus


RUN_ID_HANCHON = "11111111-1111-4111-8111-111111111111"
RUN_ID_YUKSOODANG = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 9, 10, 19, 16, tzinfo=UTC)
POLICY = SmartPlacePolicy(
    schedule_timezone="Asia/Seoul",
    daily_scheduled_time=time(4),
    start_grace=timedelta(minutes=15),
    max_duration=timedelta(minutes=180),
    expected_scopes=(
        ExpectedScope(scope_id="hanchon", scope_name="한촌설렁탕"),
        ExpectedScope(scope_id="yuksoodang", scope_name="육수당"),
    ),
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


def _run_row(
    run_id: str,
    brand_code: str,
    brand_name: str,
    *,
    started_at: datetime = datetime(2026, 9, 10, 19),
    completed_at: datetime | None = datetime(2026, 9, 10, 19, 5),
    raw_status: str = "SUCCESS",
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "scheduled_at": datetime(2026, 9, 10, 19),
        "started_at": started_at,
        "completed_at": completed_at,
        "raw_status": raw_status,
        "successful_units": 3,
        "failed_units": 0,
        "scope_id": brand_code,
        "scope_name": brand_name,
    }


def _attempt_row(
    run_id: str,
    unit_id: str,
    *,
    attempt_no: int = 1,
    raw_status: str = "SUCCESS",
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "unit_id": unit_id,
        "unit_name": unit_id,
        "attempt_no": attempt_no,
        "started_at": datetime(2026, 9, 10, 19, attempt_no),
        "completed_at": datetime(2026, 9, 10, 19, attempt_no, 30),
        "raw_status": raw_status,
        "source_count": None if unit_id == "login" else 1,
        "inserted_count": None if unit_id == "login" else 1,
        "changed_count": None if unit_id == "login" else 0,
        "unchanged_count": None if unit_id == "login" else 0,
        "committed": None if unit_id == "login" else True,
        "error_category": None,
    }


def test_list_runs_returns_one_row_per_brand_with_attempts_in_one_bulk_query() -> None:
    rows = [
        _run_row(RUN_ID_HANCHON, "hanchon", "한촌설렁탕"),
        _run_row(RUN_ID_YUKSOODANG, "yuksoodang", "육수당"),
    ]
    attempts = [
        _attempt_row(run_id, unit_id)
        for run_id in (RUN_ID_HANCHON, RUN_ID_YUKSOODANG)
        for unit_id in ("login", "normal", "pos_linked")
    ]
    repository = FixtureRepository(
        {
            SMARTPLACE_LIST_SQL: rows,
            SMARTPLACE_ATTEMPTS_FOR_RUNS_SQL: attempts,
        }
    )

    runs = SmartPlaceAdapter(repository).list_runs(limit=20)

    assert [(run.scope_id, [item.unit_id for item in run.attempts]) for run in runs] == [
        ("hanchon", ["login", "normal", "pos_linked"]),
        ("yuksoodang", ["login", "normal", "pos_linked"]),
    ]
    assert [call[0] for call in repository.calls] == [
        SMARTPLACE_LIST_SQL,
        SMARTPLACE_ATTEMPTS_FOR_RUNS_SQL,
    ]


def test_missing_expected_brand_is_not_run_only_after_start_grace() -> None:
    hanchon = _run_row(
        RUN_ID_HANCHON,
        "hanchon",
        "한촌설렁탕",
        started_at=datetime(2026, 9, 10, 18, 59),
    )
    repository = FixtureRepository(
        {
            SMARTPLACE_LIST_SQL: [hanchon],
            SMARTPLACE_ATTEMPTS_FOR_RUNS_SQL: [],
            SMARTPLACE_PRESENT_SCOPES_SQL: [{"scope_id": "hanchon"}],
        }
    )

    runs = SmartPlaceAdapter(repository, policy=POLICY, clock=lambda: NOW).list_runs(
        limit=20
    )

    assert runs[0].scope_id == "yuksoodang"
    assert runs[0].scope_name == "육수당"
    assert runs[0].status is MonitoringStatus.NOT_RUN
    assert runs[0].started_at == datetime(2026, 9, 10, 19, tzinfo=UTC)
    assert runs[0].source_count is None

    before_grace = SmartPlaceAdapter(
        FixtureRepository({SMARTPLACE_LIST_SQL: []}),
        policy=POLICY,
        clock=lambda: datetime(2026, 9, 10, 19, 14, tzinfo=UTC),
    ).list_runs(limit=20)
    assert before_grace == []


def test_stale_running_is_aborted_without_updating_the_database() -> None:
    stale = _run_row(
        RUN_ID_HANCHON,
        "hanchon",
        "한촌설렁탕",
        started_at=datetime(2026, 9, 10, 15),
        completed_at=None,
        raw_status="RUNNING",
    )
    repository = FixtureRepository(
        {
            SMARTPLACE_LIST_SQL: [stale],
            SMARTPLACE_ATTEMPTS_FOR_RUNS_SQL: [],
            SMARTPLACE_PRESENT_SCOPES_SQL: [
                {"scope_id": "hanchon"},
                {"scope_id": "yuksoodang"},
            ],
        }
    )

    runs = SmartPlaceAdapter(repository, policy=POLICY, clock=lambda: NOW).list_runs()

    assert runs[0].status is MonitoringStatus.ABORTED
    assert all(call[0].lstrip().upper().startswith(("SELECT", "WITH")) for call in repository.calls)


def test_get_run_and_latest_success_use_fixed_select_queries() -> None:
    run_row = _run_row(RUN_ID_HANCHON, "hanchon", "한촌설렁탕")
    repository = FixtureRepository(
        {
            SMARTPLACE_RUN_SQL: [run_row],
            SMARTPLACE_ATTEMPTS_SQL: [
                _attempt_row(RUN_ID_HANCHON, "login"),
            ],
            SMARTPLACE_LATEST_SUCCESS_SQL: [
                {"last_successful_check_at": datetime(2026, 9, 10, 19, 5)}
            ],
        }
    )
    adapter = SmartPlaceAdapter(repository)

    run = adapter.get_run(UUID(RUN_ID_HANCHON))

    assert run is not None and run.scope_id == "hanchon"
    assert adapter.latest_successful_check_at() == datetime(
        2026, 9, 10, 19, 5, tzinfo=UTC
    )
    assert adapter.freshness() == []
    assert adapter.readiness() is True


def test_all_smartplace_queries_are_select_only() -> None:
    from monitoring_api.adapters import smartplace

    queries = [
        value
        for name, value in vars(smartplace).items()
        if name.startswith("SMARTPLACE_") and name.endswith("_SQL")
    ]
    assert queries
    for sql in queries:
        ReadOnlyRepository._validate_select(sql)
        normalized = sql.upper()
        for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "MERGE ", "EXEC "):
            assert forbidden not in normalized
