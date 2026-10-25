from datetime import UTC, datetime, time, timedelta
import importlib
import json
from uuid import UUID, uuid5
import pytest
from monitoring_api.adapters.base import map_raw_status
from monitoring_api.config import Settings

NS = UUID("a354f224-e8ef-4ae1-9384-d78238004f78")
PARENT = uuid5(NS, '["test","20260910"]')
RUN = uuid5(PARENT, "001")
NOW = datetime(2026, 9, 10, 3, tzinfo=UTC)


def module():
    from monitoring_api.adapters import __path__

    assert any(
        __import__("pathlib").Path(p, "naver_store_hours.py").exists() for p in __path__
    ), "Store-hours adapter is missing"
    return importlib.import_module("monitoring_api.adapters.naver_store_hours")


@pytest.mark.parametrize('reason', ['INVALID_PLACE', 'HOURS_NOT_PROVIDED'])
def test_exclusion_reason_accepts_success_status(reason):
    module()._validate_counts(dict(raw_status='SUCCESS', error_category=reason,
                                   source_count=1, committed=False))


def row(**updates):
    payload = dict(
        collector_id="naver-store-hours",
        run_id=str(RUN),
        parent_run_id=str(PARENT),
        raw_status="PARTIAL_FAILURE",
        execution_kind="scheduled",
        scheduled_date="2026-09-10",
        started_at="2026-09-10T01:00:00Z",
        completed_at="2026-09-10T02:00:00Z",
        status="PARTIAL_FAILED",
        successful_units=3,
        failed_units=1,
        source_count=5,
        inserted_count=1,
        changed_count=1,
        unchanged_count=1,
        review_count=1,
        failure_count=1,
        applied_count=3,
        coverage_count=3,
        committed=True,
        successful_check_at=None,
        error_category="COLLECTION_FAILED",
        scope_id="hanchon",
        scope_name="한촌설렁탕",
        attempts=[],
    )
    payload.update(updates)
    return dict(
        run_id=str(RUN),
        parent_run_id=str(PARENT),
        source_instance="test",
        original_run_id="20260910",
        brand_code="001",
        execution_kind=payload["execution_kind"],
        started_at=datetime(2026, 9, 10, 1),
        completed_at=datetime(2026, 9, 10, 2),
        status=payload["status"],
        payload=json.dumps(payload),
    )


class Repo:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = []

    def fetch_all(self, sql, parameters=()):
        self.calls.append((sql, parameters))
        if "COUNT_BIG" in sql:
            return [{"total": len(self.rows)}]
        return self.rows

    def ping(self):
        return True


def test_partial_failure_maps_explicitly():
    assert map_raw_status("PARTIAL_FAILURE").value == "PARTIAL_FAILED"


def test_run_preserves_metrics_and_parent():
    run = module().NaverStoreHoursAdapter(Repo([row()])).list_runs()[0]
    assert run.parent_run_id == PARENT
    assert run.raw_status == "PARTIAL_FAILURE"
    assert (
        run.applied_count,
        run.review_count,
        run.failure_count,
        run.source_count,
    ) == (3, 1, 1, 5)
    assert run.status.value == "PARTIAL_FAILED"


@pytest.mark.parametrize(
    "changes",
    [
        dict(paths={"summary": "C:/secret"}),
        dict(error_category="password=secret"),
        dict(scope_name="C:/secret"),
        dict(raw_status="password=secret"),
        dict(source_count=-1),
        dict(started_at="2026-09-10T01:00:00"),
        dict(run_id="00000000-0000-0000-0000-000000000000"),
    ],
)
def test_invalid_or_leaking_payload_is_rejected(changes):
    with pytest.raises(ValueError):
        module().NaverStoreHoursAdapter(Repo([row(**changes)])).list_runs()


def test_malformed_json_rejected():
    bad = row()
    bad["payload"] = "{secret"
    with pytest.raises(ValueError):
        module().NaverStoreHoursAdapter(Repo([bad])).list_runs()


def test_bound_filters_and_select_only():
    from monitoring_api.db import ReadOnlyRepository

    repo = Repo()
    adapter = module().NaverStoreHoursAdapter(repo)
    adapter.list_runs(scope_id="hanchon", offset=5, limit=7)
    sql, parameters = repo.calls[-1]
    ReadOnlyRepository._validate_select(sql)
    assert "hanchon" not in sql and "001" in parameters
    assert parameters[-2:] == (5, 7)
    adapter.count_runs(scope_id="hanchon")
    ReadOnlyRepository._validate_select(repo.calls[-1][0])
    assert "001" in repo.calls[-1][1]


def test_preflight_is_excluded_from_current_and_freshness_queries():
    repo = Repo()
    adapter = module().NaverStoreHoursAdapter(repo)
    assert adapter.latest() is None
    assert adapter.latest_successful_check_at() is None
    assert all("ExecutionKind = 'scheduled'" in sql for sql, _ in repo.calls)


def test_connection_alone_registers_without_inferred_weekly_policy():
    from monitoring_api.composition import build_monitoring_service

    settings = Settings(
        _env_file=None,
        naver_store_hours_connection_string="Server=fixture;Database=naverDB",
    )
    assert "naver-store-hours" in build_monitoring_service(settings)._adapters


@pytest.mark.parametrize(
    "settings",
    [
        dict(naver_store_hours_weekly_scheduled_day=3),
        dict(naver_store_hours_weekly_scheduled_day=7),
    ],
)
def test_incomplete_weekly_settings_rejected(settings):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **settings)


def test_weekly_occurrence_uses_local_weekday_and_grace():
    policy = module().StoreHoursPolicy(
        schedule_timezone="Asia/Seoul",
        weekly_scheduled_day=3,
        weekly_scheduled_time=time(10),
        start_grace=timedelta(minutes=15),
        max_duration=timedelta(hours=6),
        attribution_window=timedelta(hours=2),
    )
    assert policy.occurrence(datetime(2026, 9, 10, 1, 14, tzinfo=UTC)) == datetime(
        2026, 9, 3, 1, tzinfo=UTC
    )
    assert policy.occurrence(datetime(2026, 9, 10, 1, 15, tzinfo=UTC)) == datetime(
        2026, 9, 10, 1, tzinfo=UTC
    )


def test_scope_filter_reaches_api_and_non_scoped_sources_are_empty():
    from monitoring_api.services.monitoring import MonitoringService

    repo = Repo([row()])
    adapter = module().NaverStoreHoursAdapter(repo)
    service = MonitoringService([adapter])
    result = service.list_runs(scope_id="hanchon")
    assert result.total == 1 and result.items[0].scope_id == "hanchon"
    assert all("001" in parameters for _, parameters in repo.calls)


def test_per_brand_freshness_is_not_replaced_with_collector_max():
    from monitoring_api.adapters.base import FreshnessRecord
    from monitoring_api.services.monitoring import MonitoringService

    adapter = module().NaverStoreHoursAdapter(Repo())
    service = MonitoringService([adapter])
    records = service._enrich_freshness(
        adapter,
        now=NOW,
        last_successful_check_at=NOW,
        records=[
            FreshnessRecord(
                collector_id="naver-store-hours",
                dataset_id="hanchon",
                scope_id="hanchon",
                latest_data_at=None,
            )
        ],
    )
    assert records[0].last_successful_check_at is None


def test_corrupt_source_is_isolated_and_sanitized():
    from monitoring_api.services.monitoring import MonitoringService

    class Broken(Repo):
        def fetch_all(self, *args):
            raise RuntimeError("C:/secret password=secret")

    service = MonitoringService([module().NaverStoreHoursAdapter(Broken())])
    result = service.list_runs()
    assert result.errors[0].code == "SOURCE_UNAVAILABLE"
    assert "secret" not in result.model_dump_json()


def test_http_scope_filter_is_applied_before_pagination():
    from fastapi.testclient import TestClient
    from auth_helpers import create_admin_app as create_app
    from monitoring_api.services.monitoring import MonitoringService

    repo = Repo([row()])
    client = TestClient(
        create_app(
            settings=Settings(_env_file=None),
            monitoring_service=MonitoringService(
                [module().NaverStoreHoursAdapter(repo)]
            ),
        )
    )
    response = client.get(
        "/api/v1/monitoring/runs?scope_id=hanchon&page_size=7&offset=5"
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert all("001" in parameters for _, parameters in repo.calls)
    assert repo.calls[-1][1][-2:] == (0, 12)


def test_smartplace_scope_filter_is_bound_in_count_and_list():
    from monitoring_api.adapters.smartplace import SmartPlaceAdapter
    from monitoring_api.db import ReadOnlyRepository

    repo = Repo()
    adapter = SmartPlaceAdapter(repo)
    assert adapter.count_runs(scope_id="hanchon") == 0
    assert adapter.list_runs(scope_id="hanchon") == []
    for sql, parameters in repo.calls:
        ReadOnlyRepository._validate_select(sql)
        assert "hanchon" in parameters and "hanchon" not in sql


def test_weekly_policy_absence_preserves_running_observation():
    running = row(raw_status="RUNNING", status="RUNNING", completed_at=None)
    running["completed_at"] = None
    adapter = module().NaverStoreHoursAdapter(
        Repo([running]), clock=lambda: datetime(2027, 1, 1, tzinfo=UTC)
    )
    assert adapter.latest().status.value == "RUNNING"


def test_weekly_policy_missing_brands_and_timeout_are_current_view_only():
    policy = module().StoreHoursPolicy(
        schedule_timezone="Asia/Seoul",
        weekly_scheduled_day=3,
        weekly_scheduled_time=time(10),
        start_grace=timedelta(minutes=15),
        max_duration=timedelta(hours=6),
        attribution_window=timedelta(hours=2),
    )
    adapter = module().NaverStoreHoursAdapter(Repo(), policy=policy, clock=lambda: NOW)
    assert adapter.latest().status.value == "NOT_RUN"
    assert adapter.list_runs() == []
    running = row(raw_status="RUNNING", status="RUNNING", completed_at=None)
    running["completed_at"] = None
    adapter = module().NaverStoreHoursAdapter(
        Repo([running]),
        policy=policy,
        clock=lambda: datetime(2026, 9, 10, 8, tzinfo=UTC),
    )
    assert adapter.latest().status.value == "ABORTED"
    assert adapter.list_runs()[0].status.value == "RUNNING"


def test_freshness_preserves_each_brand_and_unknown_business_timestamp():
    successful = row(
        raw_status="SUCCESS",
        status="SUCCESS",
        successful_check_at="2026-09-10T02:00:00Z",
        source_count=3,
    )
    records = module().NaverStoreHoursAdapter(Repo([successful])).freshness()
    assert records[0].last_successful_check_at == datetime(2026, 9, 10, 2, tzinfo=UTC)
    assert records[1].last_successful_check_at is None
    assert all(record.latest_data_at is None for record in records)
    assert records[0].coverage_count == 3 and records[0].source_count == 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("parent_run_id", "00000000-0000-0000-0000-000000000000"),
        ("started_at", datetime(2026, 9, 10, 0)),
        ("status", "SUCCESS"),
        ("execution_kind", "preflight-only"),
    ],
)
def test_sql_envelope_mismatch_rejected(field, value):
    bad = row()
    bad[field] = value
    with pytest.raises(ValueError):
        module().NaverStoreHoursAdapter(Repo([bad])).list_runs()


def test_all_queries_pass_read_only_parser():
    from monitoring_api.db import ReadOnlyRepository

    mod = module()
    for name in [
        "LIST_SQL",
        "COUNT_SQL",
        "STATUS_SQL",
        "RUN_SQL",
        "LATEST_SQL",
        "SUCCESS_SQL",
        "OCCURRENCE_SQL",
    ]:
        ReadOnlyRepository._validate_select(getattr(mod, name))


@pytest.mark.parametrize(
    "changes", [dict(status="FAILED"), dict(source_count=6), dict(applied_count=None)]
)
def test_incomplete_success_cannot_refresh_freshness(changes):
    bad = row(
        raw_status="SUCCESS",
        status="SUCCESS",
        source_count=3,
        successful_check_at="2026-09-10T02:00:00Z",
        **{}
    )
    payload = json.loads(bad["payload"])
    payload.update(changes)
    bad["status"] = payload["status"]
    bad["payload"] = json.dumps(payload)
    with pytest.raises(ValueError):
        module().parse_run(bad)


def test_preflight_cannot_claim_collection_metrics():
    with pytest.raises(ValueError):
        module().parse_run(row(execution_kind="preflight-only"))


def test_duplicate_stage_attempts_rejected():
    attempt = dict(
        unit_id="apply",
        unit_name="안전 대상 DB 반영",
        stage="apply",
        attempt_no=1,
        started_at="2026-09-10T01:00:00Z",
        completed_at="2026-09-10T02:00:00Z",
        raw_status="SUCCESS",
        outcome="SUCCESS",
        source_count=1,
        inserted_count=0,
        changed_count=1,
        unchanged_count=0,
        committed=True,
    )
    with pytest.raises(ValueError):
        module().parse_run(row(attempts=[attempt, attempt]))


def test_worker_attempt_linkage_and_timing_basis_are_preserved():
    child = "c06cfc6a-5c0a-5d0c-928b-511159f265de"
    attempt = dict(
        unit_id="apply:" + child,
        unit_name="안전 대상 DB 반영",
        stage="apply",
        child_run_id=child,
        timing_basis="worker-report",
        attempt_no=2,
        started_at="2026-09-10T01:00:00Z",
        completed_at="2026-09-10T02:00:00Z",
        raw_status="SUCCESS",
        outcome="SUCCESS",
        source_count=1,
        inserted_count=0,
        changed_count=1,
        unchanged_count=0,
        committed=True,
        store_codes=["0001"],
    )
    run = module().parse_run(row(attempts=[attempt]))
    assert run.attempts[0].store_codes == ["0001"]
    assert run.attempts[0].timing_basis == "worker-report"
    assert run.attempts[0].attempt_no == 2


@pytest.mark.parametrize(
    "changes",
    [
        dict(unit_name="C:/secret"),
        dict(unit_id="password=secret"),
        dict(timing_basis="password=secret"),
        dict(store_codes=["C:/secret"]),
        dict(error_category="password=secret"),
    ],
)
def test_attempt_metadata_cannot_expose_free_form_details(changes):
    attempt = dict(
        unit_id="apply",
        unit_name="안전 대상 DB 반영",
        stage="apply",
        attempt_no=1,
        started_at="2026-09-10T01:00:00Z",
        completed_at="2026-09-10T02:00:00Z",
        raw_status="SUCCESS",
        outcome="SUCCESS",
        source_count=1,
        inserted_count=0,
        changed_count=1,
        unchanged_count=0,
        committed=True,
    )
    attempt.update(changes)
    with pytest.raises(ValueError):
        module().parse_run(row(attempts=[attempt]))


def test_preflight_history_does_not_increment_collection_summary():
    from monitoring_api.services.monitoring import MonitoringService

    class SummaryRepository(Repo):
        def fetch_all(self, sql, parameters=()):
            self.calls.append((sql, parameters))
            if "GROUP BY Status" in sql:
                # 한 예약 수집 성공과 한 사전 점검 성공이 저장된 소스다.
                total = 1 if "ExecutionKind = 'scheduled'" in sql else 2
                return [{"status": "SUCCESS", "total": total}]
            return super().fetch_all(sql, parameters)

    repo = SummaryRepository()
    service = MonitoringService(
        [module().NaverStoreHoursAdapter(repo)], clock=lambda: NOW
    )
    assert service.summary().today_success_runs == 1
    assert "ExecutionKind = 'scheduled'" not in module().LIST_SQL
    assert "ExecutionKind = 'scheduled'" not in module().COUNT_SQL
