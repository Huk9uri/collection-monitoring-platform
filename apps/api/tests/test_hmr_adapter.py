from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID

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
    HMR_LATEST_SUCCESS_SQL,
    HMR_LATEST_SQL,
    HMR_LIST_SQL,
    HMR_RUN_SQL,
    HMR_STATUS_COUNTS_SQL,
    HmrAdapter,
)


RUN_ID_1 = "11111111-1111-4111-8111-111111111111"
RUN_ID_2 = "22222222-2222-4222-8222-222222222222"
RUN_ID_3 = "33333333-3333-4333-8333-333333333333"


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
                    "run_id": RUN_ID_2,
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
    assert run.scope_id is None
    assert run.scope_name is None


def test_hmr_success_with_data_is_a_canonical_success_end_to_end() -> None:
    """실제 HMR 성공 토큰은 목록/상세/필터에서 모두 정상이어야 한다."""

    repository = FixtureRepository(
        {
            HMR_LATEST_SQL: [
                {
                    "run_id": "11111111-1111-4111-8111-111111111111",
                    "scheduled_date": date(2026, 9, 8),
                    "started_at": datetime(2026, 9, 8, 5),
                    "completed_at": datetime(2026, 9, 8, 5, 3),
                    "raw_status": "SUCCESS",
                    "successful_units": 1,
                    "failed_units": 0,
                }
            ],
            HMR_ATTEMPTS_SQL: [
                {
                    "unit_id": "naver",
                    "unit_name": "naver",
                    "attempt_no": 1,
                    "started_at": datetime(2026, 9, 8, 5),
                    "completed_at": datetime(2026, 9, 8, 5, 1),
                    "raw_status": "SUCCESS_WITH_DATA",
                    "source_count": 3,
                    "inserted_count": 1,
                    "changed_count": 1,
                    "unchanged_count": 1,
                    "committed": True,
                    "error_category": None,
                }
            ],
        }
    )

    run = HmrAdapter(repository).latest()

    assert run is not None
    assert run.status is MonitoringStatus.SUCCESS
    assert run.successful_units == 1
    assert run.attempts[0].outcome is MonitoringStatus.SUCCESS
    assert "'SUCCESS_WITH_DATA'" in HMR_LIST_SQL
    assert "'SUCCESS_WITH_DATA'" in HMR_COUNT_SQL
    assert "'SUCCESS_WITH_DATA'" in HMR_ATTEMPTS_SQL


def test_hmr_success_with_data_raw_run_fallback_is_also_success() -> None:
    assert (
        derive_run_status([], raw_status="SUCCESS_WITH_DATA")
        is MonitoringStatus.SUCCESS
    )


def test_hmr_success_with_data_detail_and_retry_use_canonical_outcome() -> None:
    repository = FixtureRepository(
        {
            HMR_RUN_SQL: [
                {
                    "run_id": RUN_ID_1,
                    "scheduled_date": date(2026, 9, 8),
                    "started_at": datetime(2026, 9, 8, 5),
                    "completed_at": datetime(2026, 9, 8, 5, 3),
                    "raw_status": "SUCCESS",
                    "successful_units": 1,
                    "failed_units": 0,
                }
            ],
            HMR_ATTEMPTS_SQL: [
                {
                    "unit_id": "naver",
                    "unit_name": "naver",
                    "attempt_no": 1,
                    "started_at": datetime(2026, 9, 8, 5),
                    "completed_at": datetime(2026, 9, 8, 5, 1),
                    "raw_status": "FAILED_API",
                    "source_count": 0,
                    "inserted_count": 0,
                    "changed_count": 0,
                    "unchanged_count": 0,
                    "committed": None,
                    "error_category": "API",
                },
                {
                    "unit_id": "naver",
                    "unit_name": "naver",
                    "attempt_no": 2,
                    "started_at": datetime(2026, 9, 8, 5, 1),
                    "completed_at": datetime(2026, 9, 8, 5, 2),
                    "raw_status": "SUCCESS_WITH_DATA",
                    "source_count": 2,
                    "inserted_count": 1,
                    "changed_count": 0,
                    "unchanged_count": 1,
                    "committed": True,
                    "error_category": None,
                },
            ],
        }
    )

    run = HmrAdapter(repository).get_run(UUID(RUN_ID_1))

    assert run is not None
    assert run.status is MonitoringStatus.WARNING
    assert run.successful_units == 1
    assert run.failed_units == 0
    assert run.attempts[1].outcome is MonitoringStatus.SUCCESS
    assert run.attempts[0].committed is None


def test_hmr_daily_status_counts_use_half_open_utc_range_and_canonical_status() -> None:
    started_from = datetime(2026, 9, 8, 15, tzinfo=UTC)
    started_to = datetime(2026, 9, 9, 15, tzinfo=UTC)
    repository = FixtureRepository(
        {
            HMR_STATUS_COUNTS_SQL: [
                {"status": "SUCCESS", "total": 2},
                {"status": "FAILED", "total": 1},
            ]
        }
    )

    counts = HmrAdapter(repository).count_runs_by_status(
        started_from=started_from, started_to=started_to
    )

    assert counts == {
        MonitoringStatus.SUCCESS: 2,
        MonitoringStatus.FAILED: 1,
    }
    assert repository.calls == [
        (
            HMR_STATUS_COUNTS_SQL,
            (datetime(2026, 9, 8, 15), datetime(2026, 9, 9, 15)),
        )
    ]
    assert "runs.StartedAt >= ? AND runs.StartedAt < ?" in HMR_STATUS_COUNTS_SQL
    assert "'SUCCESS_WITH_DATA'" in HMR_STATUS_COUNTS_SQL


def test_hmr_latest_successful_check_is_not_the_latest_changed_data_time() -> None:
    checked_at = datetime(2026, 9, 8, 6)
    repository = FixtureRepository(
        {HMR_LATEST_SUCCESS_SQL: [{"last_successful_check_at": checked_at}]}
    )

    result = HmrAdapter(repository).latest_successful_check_at()

    assert result == checked_at.replace(tzinfo=UTC)
    assert "FinishedAt AS last_successful_check_at" in HMR_LATEST_SUCCESS_SQL


def test_hmr_failed_attempt_does_not_claim_that_business_data_was_uncommitted() -> None:
    repository = FixtureRepository(
        {
            HMR_LATEST_SQL: [
                {
                    "run_id": "22222222-2222-4222-8222-222222222222",
                    "scheduled_date": date(2026, 9, 8),
                    "started_at": datetime(2026, 9, 8, 5),
                    "completed_at": datetime(2026, 9, 8, 5, 3),
                    "raw_status": "FAILED",
                    "successful_units": 0,
                    "failed_units": 1,
                }
            ],
            HMR_ATTEMPTS_SQL: [
                {
                    "unit_id": "naver",
                    "unit_name": "naver",
                    "attempt_no": 1,
                    "started_at": datetime(2026, 9, 8, 5),
                    "completed_at": datetime(2026, 9, 8, 5, 1),
                    "raw_status": "FAILED_DB",
                    "source_count": 3,
                    "inserted_count": 1,
                    "changed_count": 1,
                    "unchanged_count": 1,
                    "committed": None,
                    "error_category": "DB",
                }
            ],
        }
    )

    run = HmrAdapter(repository).latest()

    assert run is not None
    assert run.attempts[0].committed is None
    assert run.attempts[0].outcome is MonitoringStatus.FAILED
    assert "ELSE NULL END AS committed" in HMR_ATTEMPTS_SQL


@pytest.mark.parametrize(
    ("raw_status", "committed", "source_count", "expected"),
    [
        (" success ", True, 1, MonitoringStatus.SUCCESS),
        (" SuCcEsS_EmPtY ", True, 0, MonitoringStatus.SUCCESS_EMPTY),
        (" success ", False, 1, MonitoringStatus.FAILED),
        ("\tSUCCESS\t", False, 1, MonitoringStatus.FAILED),
    ],
)
def test_hmr_attempt_status_normalization_matches_filter_and_committed_sql(
    raw_status: str,
    committed: bool,
    source_count: int,
    expected: MonitoringStatus,
) -> None:
    repository = FixtureRepository(
        {
            HMR_LATEST_SQL: [
                {
                    "run_id": RUN_ID_3,
                    "scheduled_date": date(2026, 9, 8),
                    "started_at": datetime(2026, 9, 8, 5),
                    "completed_at": datetime(2026, 9, 8, 5, 3),
                    "raw_status": "SUCCESS",
                    "successful_units": 1,
                    "failed_units": 0,
                }
            ],
            HMR_ATTEMPTS_SQL: [
                {
                    "unit_id": "naver",
                    "unit_name": "naver",
                    "attempt_no": 1,
                    "started_at": datetime(2026, 9, 8, 5),
                    "completed_at": datetime(2026, 9, 8, 5, 1),
                    "raw_status": raw_status,
                    "source_count": source_count,
                    "inserted_count": source_count,
                    "changed_count": 0,
                    "unchanged_count": 0,
                    "committed": committed,
                    "error_category": None,
                }
            ],
        }
    )

    run = HmrAdapter(repository).latest()

    assert run is not None
    assert run.status is expected
    normalized_filter_sql = (
        "COALESCE(UPPER(LTRIM(RTRIM(attempt.AttemptStatus))), '')"
    )
    normalized_committed_sql = (
        "COALESCE(UPPER(LTRIM(RTRIM(AttemptStatus))), '')"
    )
    committed_case = (
        f"CASE WHEN {normalized_committed_sql}\n"
        "              IN ('SUCCESS', 'SUCCESS_EMPTY', 'SUCCESS_WITH_DATA') "
        "THEN CAST(1 AS bit)\n"
        "         ELSE NULL END AS committed"
    )
    assert normalized_filter_sql in HMR_LIST_SQL
    assert normalized_filter_sql in HMR_COUNT_SQL
    assert committed_case in HMR_ATTEMPTS_SQL
    assert committed_case in HMR_ATTEMPTS_FOR_RUNS_SQL


def _attempt(unit_id: str, status: str, source_count: int = 1) -> CollectorAttempt:
    outcome = (
        MonitoringStatus.SUCCESS_EMPTY
        if status == "SUCCESS_EMPTY"
        else MonitoringStatus.SUCCESS
        if status.startswith("SUCCESS")
        else MonitoringStatus.FAILED
    )
    return CollectorAttempt(
        unit_id=unit_id,
        unit_name=unit_id,
        attempt_no=1,
        started_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
        completed_at=datetime(2026, 9, 8, 1, 1, tzinfo=UTC),
        raw_status=status,
        outcome=outcome,
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
        status=MonitoringStatus.PARTIAL_FAILED,
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
                "PARTIAL_FAILED",
                "PARTIAL_FAILED",
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
        started_from=started_from,
        started_to=started_to,
        status=MonitoringStatus.WARNING,
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
                "WARNING",
                "WARNING",
            ),
        )
    ]
    assert "WHEN 'PARTIAL' THEN 'PARTIAL_FAILED'" in HMR_COUNT_SQL
    assert "dbo.CHANNEL_COLLECTION_ATTEMPT" in HMR_COUNT_SQL
    assert "AttemptNo" in HMR_COUNT_SQL
    assert HMR_LIST_SQL.index("AND (? IS NULL OR CASE") < HMR_LIST_SQL.index(
        "OFFSET ? ROWS"
    )


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
            outcome=MonitoringStatus.SUCCESS,
            source_count=1,
            inserted_count=1,
            changed_count=0,
            unchanged_count=0,
            committed=True,
        )
    with pytest.raises(ValueError, match="UTC"):
        CollectorRun(
            collector_id="hmr",
            run_id=RUN_ID_1,
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
            latest_data_at=timestamp,
        )
    with pytest.raises(ValueError, match="UTC"):
        CollectorAttempt(
            unit_id="naver",
            unit_name="네이버",
            attempt_no=1,
            started_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
            completed_at=timestamp,
            raw_status="SUCCESS",
            outcome=MonitoringStatus.SUCCESS,
            source_count=1,
            inserted_count=1,
            changed_count=0,
            unchanged_count=0,
            committed=True,
        )
    with pytest.raises(ValueError, match="UTC"):
        CollectorRun(
            collector_id="hmr",
            run_id=RUN_ID_1,
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
            "raw_status": "SUCCESS_WITH_DATA",
            "successful_units": 1,
            "failed_units": 0,
        }
        for run_id in (RUN_ID_1, RUN_ID_2)
    ]
    attempt_rows = [
        {
            "run_id": run_id,
            "unit_id": "naver",
            "unit_name": "naver",
            "attempt_no": 1,
            "started_at": datetime(2026, 9, 8, 5),
            "completed_at": datetime(2026, 9, 8, 5, 1),
            "raw_status": "SUCCESS_WITH_DATA",
            "source_count": 1,
            "inserted_count": 1,
            "changed_count": 0,
            "unchanged_count": 0,
            "committed": True,
            "error_category": None,
        }
        for run_id in (RUN_ID_1, RUN_ID_2)
    ]
    repository = FixtureRepository(
        {
            HMR_LIST_SQL: run_rows,
            HMR_ATTEMPTS_FOR_RUNS_SQL: attempt_rows,
        }
    )

    runs = HmrAdapter(repository).list_runs(limit=2)

    assert [run.run_id for run in runs] == [UUID(RUN_ID_1), UUID(RUN_ID_2)]
    assert [len(run.attempts) for run in runs] == [1, 1]
    assert [call[0] for call in repository.calls] == [
        HMR_LIST_SQL,
        HMR_ATTEMPTS_FOR_RUNS_SQL,
    ]
    assert repository.calls[1][1] == (f'["{RUN_ID_1}", "{RUN_ID_2}"]',)


def test_all_hmr_fixed_queries_pass_the_read_only_validator() -> None:
    from monitoring_api.db import ReadOnlyRepository

    for sql in (
        HMR_LATEST_SQL,
        HMR_LIST_SQL,
        HMR_COUNT_SQL,
        HMR_STATUS_COUNTS_SQL,
        HMR_LATEST_SUCCESS_SQL,
        HMR_RUN_SQL,
        HMR_ATTEMPTS_SQL,
        HMR_ATTEMPTS_FOR_RUNS_SQL,
        HMR_FRESHNESS_SQL,
    ):
        ReadOnlyRepository._validate_select(sql)


def test_hmr_run_queries_have_a_total_candidate_order() -> None:
    order = "ORDER BY StartedAt DESC, CONVERT(char(36), RunId) DESC"
    assert order in HMR_LATEST_SQL
    assert order in HMR_LIST_SQL
