from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
import pytest
from monitoring_api.adapters.naver_review import NaverReviewAdapter
from monitoring_api.models import MonitoringStatus
from monitoring_api.services.monitoring import MonitoringService
from monitoring_api.services.policy import MonitoringPolicy
from test_monitoring_policy import NOW, PolicyAdapter, make_run, configured_policy
from test_naver_review_adapter import Repository, RUN, OTHER


def service_with(policy, status=MonitoringStatus.SUCCESS):
    run = make_run(status)
    adapter = PolicyAdapter(latest=run, latest_data_at=NOW - timedelta(days=3))
    service = MonitoringService([adapter], policies={'policy': configured_policy()}, clock=lambda: NOW)
    service.policy_service = Mock()
    service.policy_service.get.return_value = {'policy': policy.model_dump(mode='json'), 'version':'0000000000000001',
        'policy_source':'db', 'warning':None, 'updated_at':NOW.isoformat()}
    return service, run


def policy(**extra):
    return MonitoringPolicy(timezone_name='Asia/Seoul', start_grace_minutes=5,
        schedule_attribution_window_minutes=180, schedules=[{'weekday_number':2, 'scheduled_time':'10:00'}], **extra)


def test_db_freshness_does_not_mix_env_and_canonical_run_is_unchanged():
    service, run = service_with(policy(freshness={}))
    result = service.collectors().items[0]
    assert result.status == MonitoringStatus.SUCCESS
    assert not result.freshness_overdue
    assert result.policy_source == 'db'
    assert run.status == MonitoringStatus.SUCCESS


def test_db_freshness_applies_to_both_overview_and_freshness_endpoint():
    service, run = service_with(policy(freshness={'orders':30}))
    assert service.collectors().items[0].status == MonitoringStatus.WARNING
    assert service.freshness().items[0].freshness_overdue
    assert run.status == MonitoringStatus.SUCCESS


def test_disabled_schedule_does_not_mark_prior_execution_missing():
    service, _ = service_with(policy(monitoring_enabled=False))
    assert service.collectors().items[0].status == MonitoringStatus.SUCCESS


@pytest.fixture
def review_repo():
    repository = Repository()
    yield repository
    repository.db.close()


def review_service(repository, *, now=datetime(2026, 9, 16, 0, tzinfo=UTC), **overrides):
    class InlineRunner:
        def run(self, calls, **_):
            return {key: operation() for key, operation in calls}, set()

    saved = MonitoringPolicy(timezone_name='Asia/Seoul', start_grace_minutes=30,
        schedule_attribution_window_minutes=360, max_duration_minutes=60,
        schedules=overrides.pop('schedules', [{'weekday_number': day, 'scheduled_time': '07:00'} for day in range(1, 8)]),
        **overrides)
    service = MonitoringService([NaverReviewAdapter(repository, review_kind='visitor')],
        clock=lambda: now, runner=InlineRunner())
    service.policy_service = Mock()
    service.policy_service.get.return_value = {'policy': saved.model_dump(mode='json'),
        'version': '0000000000000001', 'policy_source': 'db', 'warning': None, 'updated_at': None}
    return service


@pytest.mark.parametrize('execution,target', [
    ('manual', {}),
    ('manual', {'TargetKind': 'single-store', 'TargetPlaceId': '777'}),
    ('manual', {'TargetKind': 'date-range', 'TargetDateFrom': '2026-09-01', 'TargetDateTo': '2026-09-15'}),
    ('backfill', {'TargetKind': 'date-range', 'TargetDateFrom': '2026-09-01', 'TargetDateTo': '2026-09-15'}),
])
def test_manual_success_does_not_hide_missing_scheduled_slot(review_repo, execution, target):
    review_repo.run(execution=execution, **target)
    service = review_service(review_repo)
    summary = service.collectors().items[0]
    assert summary.status == MonitoringStatus.NOT_RUN
    assert summary.latest_run is None
    assert summary.last_successful_check_at is None
    assert service.summary().today_success_runs == 0
    assert service.list_runs().items[0].execution_kind == execution
    assert service.get_run('naver-review-visitor', RUN).items[0].target_kind == target.get('TargetKind', 'all-stores')


@pytest.mark.parametrize('stored,expected', [('FAILED', 'FAILED'), ('RUNNING', 'ABORTED')])
def test_newer_manual_success_keeps_scheduled_failure_or_stale_running(review_repo, stored, expected):
    review_repo.run(Status=stored, CompletedAt=None, SuccessfulStoreCount=0)
    review_repo.run(OTHER, execution='manual', StartedAt='2026-09-15 23:00:00',
        CompletedAt='2026-09-15 23:10:00')
    service = review_service(review_repo)
    summary = service.collectors().items[0]
    assert summary.status == expected
    assert summary.latest_run.run_id == RUN
    assert summary.latest_run.status == stored
    assert service.get_run('naver-review-visitor', RUN).items[0].status == stored
    assert service.summary().today_success_runs == 0


def test_review_freshness_uses_business_date_and_scheduled_success_only(review_repo):
    review_repo.run()
    review_repo.run(OTHER, execution='manual', StartedAt='2026-09-15 23:00:00',
        CompletedAt='2026-09-15 23:10:00')
    review_repo.db.execute("INSERT INTO dbo.naver_review_visitor VALUES ('2026-09-15')")
    service = review_service(review_repo, freshness={'visitor-reviews': 60})
    summary = service.collectors().items[0]
    assert summary.status == MonitoringStatus.WARNING
    assert summary.latest_run.run_id == RUN
    assert summary.last_successful_check_at == datetime(2026, 9, 15, 22, 10, tzinfo=UTC)
    assert summary.latest_data_at == datetime(2026, 9, 14, 15, tzinfo=UTC)
    assert summary.freshness[0].last_successful_check_at == summary.last_successful_check_at
    assert summary.freshness_overdue and service.freshness().items[0].freshness_overdue


def test_scheduled_run_for_prior_day_cannot_fill_current_slot(review_repo):
    review_repo.run(ScheduledAt='2026-09-14 22:00:00')
    summary = review_service(review_repo).collectors().items[0]
    assert summary.status == MonitoringStatus.NOT_RUN


def test_before_grace_keeps_previous_scheduled_status(review_repo):
    review_repo.run(ScheduledAt='2026-09-14 22:00:00', StartedAt='2026-09-14 22:01:00',
        CompletedAt='2026-09-14 22:10:00')
    summary = review_service(review_repo, now=datetime(2026, 9, 15, 22, 29, tzinfo=UTC)).collectors().items[0]
    assert summary.status == MonitoringStatus.SUCCESS


@pytest.mark.parametrize('status', ['RUNNING', 'SUCCESS', 'SUCCESS_EMPTY'])
def test_disabled_review_policy_keeps_stored_status_and_skips_freshness(review_repo, status):
    review_repo.run(Status=status, CompletedAt=None if status == 'RUNNING' else '2026-09-15 22:10:00')
    review_repo.db.execute("INSERT INTO dbo.naver_review_visitor VALUES ('2026-09-01')")
    service = review_service(review_repo, monitoring_enabled=False, freshness={'visitor-reviews': 1})
    summary = service.collectors().items[0]
    assert summary.status == status
    assert summary.latest_run.status == status
    assert summary.latest_run.source_count == 3
    assert not summary.freshness_overdue
    assert not service.freshness().items[0].freshness_overdue
    assert summary.latest_data_at == datetime(2026, 8, 31, 15, tzinfo=UTC)


@pytest.mark.parametrize('status', [MonitoringStatus.RUNNING, MonitoringStatus.SUCCESS, MonitoringStatus.SUCCESS_EMPTY])
def test_disabled_legacy_policy_skips_duration_and_freshness(status):
    service, stored = service_with(policy(monitoring_enabled=False, max_duration_minutes=1,
        freshness={'orders': 1}), status)
    summary = service.collectors().items[0]
    assert summary.status == stored.status
    assert summary.latest_run == stored
    assert not summary.freshness_overdue
    assert not service.freshness().items[0].freshness_overdue


@pytest.mark.parametrize('scheduled_at,expected', [
    ('2026-09-15 22:00:00', MonitoringStatus.NOT_RUN),
    ('2026-09-15 23:00:00', MonitoringStatus.SUCCESS),
])
def test_review_declared_slot_not_actual_start_decides_multi_slot_attribution(review_repo, scheduled_at, expected):
    # 07:00 회차가 08:05에 지연 시작해도 08:00 회차를 대신하지 않는다.
    review_repo.run(ScheduledAt=scheduled_at, StartedAt='2026-09-15 23:05:00',
        CompletedAt='2026-09-15 23:10:00')
    service = review_service(review_repo, schedules=[
        {'weekday_number': 3, 'scheduled_time': '07:00'},
        {'weekday_number': 3, 'scheduled_time': '08:00'},
    ])
    assert service.collectors().items[0].status == expected


def test_legacy_scheduled_run_without_declared_timestamp_keeps_start_time_attribution():
    service, run = service_with(policy())
    run.execution_kind = 'scheduled'
    assert run.scheduled_at is None
    assert service.collectors().items[0].status == MonitoringStatus.SUCCESS
