from datetime import UTC, datetime
import pytest
from pydantic import ValidationError
from monitoring_api.services.policy import MonitoringPolicy, Schedule, previous_occurrence
from monitoring_api.services.policy import PolicyService
from monitoring_api.control_db import ControlDatabaseUnavailable
from unittest.mock import Mock


def policy(**values):
    return MonitoringPolicy(timezone_name='Asia/Seoul', start_grace_minutes=10,
        schedule_attribution_window_minutes=60, schedules=[Schedule(weekday_number=1, scheduled_time='09:00')], **values)


def test_weekly_occurrence_crosses_utc_day_boundary():
    assert previous_occurrence(policy(), datetime(2026,9,14,1,tzinfo=UTC)) == datetime(2026,9,14,0,tzinfo=UTC)
    assert previous_occurrence(policy(), datetime(2026,9,13,23,tzinfo=UTC)) == datetime(2026,9,7,0,tzinfo=UTC)


def test_duplicate_or_missing_active_schedules_rejected():
    with pytest.raises(ValidationError):
        MonitoringPolicy(timezone_name='Asia/Seoul', start_grace_minutes=5,
                         schedule_attribution_window_minutes=60, schedules=[])
    with pytest.raises(ValidationError):
        MonitoringPolicy(timezone_name='Asia/Seoul', start_grace_minutes=5,
            schedule_attribution_window_minutes=60,
            schedules=[Schedule(weekday_number=1, scheduled_time='09:00')] * 2)


def test_explicit_disabled_policy_has_no_occurrence():
    assert previous_occurrence(policy(monitoring_enabled=False), datetime.now(UTC)) is None


def test_db_cache_expiry_failure_and_recovery_are_distinct():
    clock = Mock(return_value=0)
    repository = Mock()
    record = {'policy': policy().model_dump(mode='json'), 'version': '0000000000000001'}
    repository.get.return_value = record
    service = PolicyService(repository, {}, {'fcdaum': set()}, clock=clock)
    assert service.get('fcdaum')['policy_source'] == 'db'
    clock.return_value = 59
    assert service.get('fcdaum')['policy_source'] == 'db'
    assert repository.get.call_count == 1
    clock.return_value = 60
    repository.get.side_effect = ControlDatabaseUnavailable()
    assert service.get('fcdaum')['policy_source'] == 'cached'
    repository.get.side_effect = None
    repository.get.return_value = None
    assert service.get('fcdaum')['policy_source'] == 'none'


def test_no_snapshot_falls_back_and_unknown_dataset_is_rejected():
    repository = Mock()
    repository.get.side_effect = ControlDatabaseUnavailable()
    service = PolicyService(repository, {'fcdaum': policy()}, {'fcdaum': {'reports'}})
    assert service.get('fcdaum')['policy_source'] == 'env'
    assert service.get('fcdaum')['warning']
    with pytest.raises(ValueError):
        service.validate('fcdaum', policy(freshness={'unknown': 10}))


def test_multiple_runs_are_attributed_to_nearest_prior_occurrence():
    value = MonitoringPolicy(timezone_name='Asia/Seoul', start_grace_minutes=5,
        schedule_attribution_window_minutes=60, schedules=[
            {'weekday_number': 1, 'scheduled_time': '09:00'}, {'weekday_number': 1, 'scheduled_time': '12:00'}])
    assert previous_occurrence(value, datetime(2026,9,14,4,tzinfo=UTC)) == datetime(2026,9,14,3,tzinfo=UTC)


def test_spring_dst_nonexistent_time_is_skipped():
    value = MonitoringPolicy(timezone_name='America/New_York', start_grace_minutes=5,
        schedule_attribution_window_minutes=60, schedules=[{'weekday_number': 7, 'scheduled_time': '02:30'}])
    assert previous_occurrence(value, datetime(2026,3,8,9,tzinfo=UTC)) == datetime(2026,3,1,7,30,tzinfo=UTC)
