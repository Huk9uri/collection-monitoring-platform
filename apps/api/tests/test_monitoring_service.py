from datetime import UTC, date, datetime

import pytest

from monitoring_api.adapters.base import (
    CollectorAdapter,
    CollectorRun,
    FreshnessRecord,
    MonitoringStatus,
)
from monitoring_api.services.monitoring import MonitoringService, UnknownCollectorError


class AvailableAdapter:
    collector_id = "available"
    display_name = "정상 수집기"

    def latest(self) -> CollectorRun | None:
        return CollectorRun(
            collector_id=self.collector_id,
            run_id="run-ok",
            scheduled_date=date(2026, 9, 8),
            started_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
            completed_at=datetime(2026, 9, 8, 1, 1, tzinfo=UTC),
            status=MonitoringStatus.SUCCESS,
            successful_units=1,
            failed_units=0,
            source_count=1,
            inserted_count=1,
            changed_count=0,
            unchanged_count=0,
        )

    def list_runs(self, **_: object) -> list[CollectorRun]:
        latest = self.latest()
        return [latest] if latest is not None else []

    def get_run(self, run_id: str) -> CollectorRun | None:
        return self.latest() if run_id == "run-ok" else None

    def freshness(self) -> list[FreshnessRecord]:
        return [
            FreshnessRecord(
                collector_id=self.collector_id,
                dataset_id="orders",
                latest_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
            )
        ]

    def readiness(self) -> bool:
        return True


class UnavailableAdapter(AvailableAdapter):
    collector_id = "unavailable"
    display_name = "장애 수집기"

    def latest(self) -> CollectorRun | None:
        raise RuntimeError("Server=db;Password=secret; SELECT * FROM private")


def test_adapter_implements_the_full_collector_contract() -> None:
    adapter: CollectorAdapter = AvailableAdapter()
    assert adapter.readiness() is True


def test_one_source_failure_keeps_other_latest_result_and_sanitizes_error() -> None:
    service = MonitoringService([AvailableAdapter(), UnavailableAdapter()])

    result = service.latest()

    assert [run.collector_id for run in result.items] == ["available"]
    assert result.errors[0].collector_id == "unavailable"
    assert result.errors[0].code == "SOURCE_UNAVAILABLE"
    assert "secret" not in result.errors[0].message
    assert "SELECT" not in result.errors[0].message


def test_service_queries_only_registered_adapters() -> None:
    service = MonitoringService([AvailableAdapter()])

    with pytest.raises(UnknownCollectorError):
        service.get_run("not-registered", "run-ok")


def test_duplicate_collector_registration_is_rejected() -> None:
    with pytest.raises(ValueError, match="available"):
        MonitoringService([AvailableAdapter(), AvailableAdapter()])
