from datetime import timedelta
from unittest.mock import Mock
from monitoring_api.models import MonitoringStatus
from monitoring_api.services.monitoring import MonitoringService
from monitoring_api.services.policy import MonitoringPolicy
from test_monitoring_policy import NOW, PolicyAdapter, make_run, configured_policy


def service_with(policy):
    run = make_run(MonitoringStatus.SUCCESS)
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
