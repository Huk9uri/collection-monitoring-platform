from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from monitoring_api.adapters.base import (
    CollectorAdapter,
    CollectorRun,
    FreshnessRecord,
    MonitoringStatus,
)
from monitoring_api.services.monitoring import MonitoringService, UnknownCollectorError


ORDERED_RUN_IDS = {
    "run-x": UUID("00000000-0000-4000-8000-000000000001"),
    "run-y": UUID("00000000-0000-4000-8000-000000000002"),
    "run-z": UUID("00000000-0000-4000-8000-000000000003"),
}


def run_uuid(label: str) -> UUID:
    return ORDERED_RUN_IDS.get(label, uuid5(NAMESPACE_URL, f"monitoring:{label}"))


class AvailableAdapter:
    collector_id = "available"
    display_name = "정상 수집기"

    def latest(self) -> CollectorRun | None:
        return CollectorRun(
            collector_id=self.collector_id,
            run_id=run_uuid("run-ok"),
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

    def count_runs(self, **_: object) -> int:
        return 1

    def get_run(self, run_id: UUID) -> CollectorRun | None:
        return self.latest() if run_id == run_uuid("run-ok") else None

    def freshness(self) -> list[FreshnessRecord]:
        return [
            FreshnessRecord(
                collector_id=self.collector_id,
                dataset_id="orders",
                latest_data_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
            )
        ]

    def readiness(self) -> bool:
        return True


class UnavailableAdapter(AvailableAdapter):
    collector_id = "unavailable"
    display_name = "장애 수집기"

    def latest(self) -> CollectorRun | None:
        raise RuntimeError("Server=db;Password=secret; SELECT * FROM private")


class PagedAdapter(AvailableAdapter):
    def __init__(self, collector_id: str, runs: list[CollectorRun]) -> None:
        self.collector_id = collector_id
        self.display_name = collector_id
        self.runs = runs
        self.list_calls: list[dict[str, object]] = []
        self.count_calls: list[dict[str, object]] = []

    def list_runs(self, **conditions: object) -> list[CollectorRun]:
        self.list_calls.append(conditions)
        offset = int(conditions["offset"])
        limit = int(conditions["limit"])
        status = conditions.get("status")
        filtered = [
            run for run in self.runs if status is None or run.status is status
        ]
        return filtered[offset : offset + limit]

    def count_runs(self, **conditions: object) -> int:
        self.count_calls.append(conditions)
        status = conditions.get("status")
        return sum(status is None or run.status is status for run in self.runs)


def make_run(
    collector_id: str,
    run_id: str,
    minute: int,
    status: MonitoringStatus = MonitoringStatus.SUCCESS,
) -> CollectorRun:
    started_at = datetime(2026, 9, 8, 1, tzinfo=UTC) - timedelta(minutes=minute)
    return CollectorRun(
        collector_id=collector_id,
        run_id=run_uuid(run_id),
        scheduled_date=date(2026, 9, 8),
        started_at=started_at,
        completed_at=started_at + timedelta(minutes=1),
        status=status,
        successful_units=1,
        failed_units=0,
        source_count=1,
        inserted_count=1,
        changed_count=0,
        unchanged_count=0,
    )


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
        service.get_run("not-registered", run_uuid("run-ok"))


def test_duplicate_collector_registration_is_rejected() -> None:
    with pytest.raises(ValueError, match="available"):
        MonitoringService([AvailableAdapter(), AvailableAdapter()])


def test_all_collectors_runs_use_one_global_order_and_page() -> None:
    first = PagedAdapter(
        "first",
        [
            make_run("first", "first-0", 0),
            make_run("first", "first-2", 2),
            make_run("first", "first-4", 4),
            make_run("first", "first-6", 6),
        ],
    )
    second = PagedAdapter(
        "second",
        [
            make_run("second", "second-1", 1),
            make_run("second", "second-3", 3),
            make_run("second", "second-5", 5),
            make_run("second", "second-7", 7),
        ],
    )
    service = MonitoringService([first, second])

    result = service.list_runs(offset=2, limit=3)

    assert [run.run_id for run in result.items] == [
        run_uuid("first-2"),
        run_uuid("second-3"),
        run_uuid("first-4"),
    ]
    assert first.list_calls == [
        {
            "started_from": None,
            "started_to": None,
            "offset": 0,
            "limit": 5,
        }
    ]
    assert second.list_calls == first.list_calls
    assert result.total == 8
    assert first.count_calls == [{"started_from": None, "started_to": None}]
    assert second.count_calls == first.count_calls


def test_runs_excludes_failed_adapter_from_total_and_reports_failure() -> None:
    class BrokenAdapter(PagedAdapter):
        def list_runs(self, **conditions: object) -> list[CollectorRun]:
            del conditions
            raise RuntimeError("Password=secret")

    healthy = PagedAdapter("healthy", [make_run("healthy", "ok", 0)])
    broken = BrokenAdapter("broken", [make_run("broken", "hidden", 1)])

    result = MonitoringService([healthy, broken]).list_runs()

    assert result.total == 1
    assert [run.run_id for run in result.items] == [run_uuid("ok")]
    assert [error.collector_id for error in result.errors] == ["broken"]


def test_status_filter_is_applied_before_adapter_pagination_and_count() -> None:
    adapter = PagedAdapter(
        "collector",
        [
            make_run("collector", "success-first-page", 0),
            make_run(
                "collector",
                "failed-second-page",
                1,
                MonitoringStatus.FAILED,
            ),
        ],
    )

    result = MonitoringService([adapter]).list_runs(
        status=MonitoringStatus.FAILED,
        offset=0,
        limit=1,
    )

    assert [run.run_id for run in result.items] == [
        run_uuid("failed-second-page")
    ]
    assert result.total == 1
    assert adapter.count_calls == [
        {
            "started_from": None,
            "started_to": None,
            "status": MonitoringStatus.FAILED,
        }
    ]
    assert adapter.list_calls == [
        {
            "started_from": None,
            "started_to": None,
            "status": MonitoringStatus.FAILED,
            "offset": 0,
            "limit": 1,
        }
    ]


def test_same_started_at_candidate_boundary_uses_run_id_desc_order() -> None:
    tied_at = datetime(2026, 9, 8, 1, tzinfo=UTC)

    def tied_run(collector_id: str, run_id: str) -> CollectorRun:
        return make_run(collector_id, run_id, 0).model_copy(
            update={"started_at": tied_at}
        )

    first = PagedAdapter(
        "z-collector",
        [
            tied_run("z-collector", "run-z"),
            tied_run("z-collector", "run-y"),
            tied_run("z-collector", "run-x"),
        ],
    )
    second = PagedAdapter(
        "a-collector",
        [tied_run("a-collector", "run-z"), tied_run("a-collector", "run-y")],
    )

    result = MonitoringService([first, second]).list_runs(offset=1, limit=1)

    assert [run.run_id for run in result.items] == [run_uuid("run-y")]
    assert first.list_calls[0]["limit"] == 2
    assert second.list_calls[0]["limit"] == 2
