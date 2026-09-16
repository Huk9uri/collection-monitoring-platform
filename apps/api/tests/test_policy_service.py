from datetime import UTC, datetime
import pytest
from pydantic import ValidationError
from monitoring_api.services.policy import MonitoringPolicy, Schedule, previous_occurrence
from monitoring_api.services.policy import PolicyService
from monitoring_api.control_db import ControlDatabaseUnavailable
from monitoring_api.config import Settings
from monitoring_api.policy_composition import build_policy_service
import monitoring_api.policy_composition as policy_composition
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


@pytest.mark.parametrize(
    ("collector_id", "scheduled_time", "dataset_id"),
    [
        ("naver-review-visitor", "07:00:00", "visitor-reviews"),
        ("naver-review-blog", "07:30:00", "blog-reviews"),
    ],
)
def test_review_policy_seed_is_available_for_control_db_registration(
    collector_id: str,
    scheduled_time: str,
    dataset_id: str,
) -> None:
    service = build_policy_service(Settings(_env_file=None), [collector_id])

    result = service.get(collector_id)

    assert service.datasets[collector_id] == {dataset_id}
    assert result["policy_source"] == "env"
    assert result["policy"] == {
        "timezone_name": "Asia/Seoul",
        "max_duration_minutes": 360,
        "start_grace_minutes": 30,
        "schedule_attribution_window_minutes": 360,
        "monitoring_enabled": True,
        "schedules": [
            {
                "weekday_number": weekday,
                "scheduled_time": scheduled_time,
                "schedule_enabled": True,
            }
            for weekday in range(1, 8)
        ],
        "freshness": {},
    }


def test_control_db_policy_has_priority_over_review_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored_policy = MonitoringPolicy(
        timezone_name="Asia/Seoul",
        start_grace_minutes=10,
        schedule_attribution_window_minutes=60,
        max_duration_minutes=120,
        schedules=[Schedule(weekday_number=1, scheduled_time="08:00")],
    ).model_dump(mode="json")
    monkeypatch.setattr(
        policy_composition.ConfiguredPolicyRepository,
        "get",
        lambda self, collector_id: {
            "collector_id": collector_id,
            "policy": stored_policy,
            "version": "0000000000000001",
            "updated_at": "2026-09-16T00:00:00+00:00",
        },
    )
    service = build_policy_service(
        Settings(_env_file=None), ["naver-review-visitor"]
    )

    result = service.get("naver-review-visitor")

    assert result["policy_source"] == "db"
    assert result["policy"]["schedules"] == [
        {
            "weekday_number": 1,
            "scheduled_time": "08:00:00",
            "schedule_enabled": True,
        }
    ]
    assert result["policy"]["max_duration_minutes"] == 120
