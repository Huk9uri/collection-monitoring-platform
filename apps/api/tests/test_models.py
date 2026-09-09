from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from monitoring_api.adapters.base import CollectorRun
from monitoring_api.models import (
    MonitoringStatus,
    RunTimeRange,
    StatusSeverity,
    status_severity,
)


def test_run_preserves_scope_and_unknown_counts() -> None:
    """브랜드 실행과 실패 전 미확정 집계를 공개 계약에서 보존한다."""

    run = CollectorRun(
        collector_id="smartplace",
        run_id="11111111-1111-4111-8111-111111111111",
        scheduled_date=date(2026, 9, 9),
        started_at=datetime(2026, 9, 9, 1, tzinfo=UTC),
        completed_at=None,
        status=MonitoringStatus.RUNNING,
        successful_units=0,
        failed_units=0,
        scope_id="hanchon",
        scope_name="한촌설렁탕",
        source_count=None,
        inserted_count=None,
        changed_count=None,
        unchanged_count=None,
    )

    assert run.scope_id == "hanchon"
    assert run.scope_name == "한촌설렁탕"
    assert run.source_count is None
    assert run.inserted_count is None
    assert run.changed_count is None
    assert run.unchanged_count is None


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
