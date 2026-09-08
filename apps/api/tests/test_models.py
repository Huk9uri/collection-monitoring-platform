from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from monitoring_api.models import (
    MonitoringStatus,
    RunTimeRange,
    StatusSeverity,
    status_severity,
)


def test_monitoring_status_has_the_eight_public_contract_values() -> None:
    assert [status.value for status in MonitoringStatus] == [
        "SUCCESS",
        "SUCCESS_EMPTY",
        "WARNING",
        "PARTIAL_FAILED",
        "FAILED",
        "RUNNING",
        "ABORTED",
        "NOT_RUN",
    ]


def test_partial_failed_is_an_incident_not_a_warning() -> None:
    assert status_severity(MonitoringStatus.PARTIAL_FAILED) is StatusSeverity.INCIDENT


def test_run_time_range_accepts_only_utc_timestamps() -> None:
    utc_time = datetime(2026, 9, 8, 1, 2, 3, tzinfo=UTC)

    model = RunTimeRange(started_at=utc_time, completed_at=utc_time + timedelta(minutes=1))

    assert model.started_at.tzinfo is UTC
    assert model.completed_at is not None
    assert model.completed_at.tzinfo is UTC


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 9, 8, 1, 2, 3),
        datetime(2026, 9, 8, 10, 2, 3, tzinfo=timezone(timedelta(hours=9))),
    ],
)
def test_run_time_range_rejects_non_utc_timestamps(timestamp: datetime) -> None:
    with pytest.raises(ValidationError, match="UTC"):
        RunTimeRange(started_at=timestamp)
