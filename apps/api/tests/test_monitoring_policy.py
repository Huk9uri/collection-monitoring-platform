from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

import pytest

from monitoring_api.adapters.base import CollectorRun, FreshnessRecord
from monitoring_api.models import MonitoringStatus
from monitoring_api.services.monitoring import (
    BoundedParallelRunner,
    CollectorPolicy,
    MonitoringService,
)

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 9, 8, 3, tzinfo=UTC)


class PolicyAdapter:
    collector_id = "policy"
    display_name = "정책 수집기"

    def __init__(
        self,
        *,
        latest: CollectorRun | None,
        last_successful_check_at: datetime | None = None,
        latest_data_at: datetime | None = None,
        counts: dict[MonitoringStatus, int] | None = None,
    ) -> None:
        self._latest = latest
        self._last_successful_check_at = last_successful_check_at
        self._latest_data_at = latest_data_at
        self._counts = counts or {}
        self.count_boundaries: list[tuple[datetime, datetime]] = []

    def latest(self) -> CollectorRun | None:
        return self._latest

    def latest_successful_check_at(self) -> datetime | None:
        return self._last_successful_check_at

    def list_runs(self, **_: object) -> list[CollectorRun]:
        return [] if self._latest is None else [self._latest]

    def count_runs(self, **_: object) -> int:
        return 0 if self._latest is None else 1

    def count_runs_by_status(
        self, *, started_from: datetime, started_to: datetime
    ) -> dict[MonitoringStatus, int]:
        self.count_boundaries.append((started_from, started_to))
        return self._counts

    def get_run(self, run_id: UUID) -> CollectorRun | None:
        return self._latest if self._latest and run_id == self._latest.run_id else None

    def freshness(self) -> list[FreshnessRecord]:
        return [
            FreshnessRecord(
                collector_id=self.collector_id,
                dataset_id="orders",
                latest_data_at=self._latest_data_at,
            )
        ]

    def readiness(self) -> bool:
        return True


def make_run(
    status: MonitoringStatus,
    *,
    started_at: datetime = NOW - timedelta(minutes=30),
    scheduled_date: date = date(2026, 9, 8),
) -> CollectorRun:
    return CollectorRun(
        collector_id="policy",
        run_id=RUN_ID,
        scheduled_date=scheduled_date,
        started_at=started_at,
        completed_at=None if status is MonitoringStatus.RUNNING else started_at + timedelta(minutes=5),
        status=status,
        successful_units=1,
        failed_units=0,
        source_count=1,
        inserted_count=0,
        changed_count=0,
        unchanged_count=1,
    )


def configured_policy() -> CollectorPolicy:
    return CollectorPolicy(
        schedule_timezone="Asia/Seoul",
        daily_scheduled_time=time(10, 0),
        max_duration=timedelta(hours=1),
        freshness_sla={"orders": timedelta(hours=1)},
    )


@pytest.mark.parametrize(
    "values",
    [
        {"schedule_timezone": "Asia/Seoul"},
        {"daily_scheduled_time": time(10, 0)},
    ],
)
def test_schedule_policy_requires_timezone_and_time_as_a_pair(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="함께"):
        CollectorPolicy(**values)


def test_due_collector_without_history_is_not_run() -> None:
    adapter = PolicyAdapter(latest=None)
    service = MonitoringService(
        [adapter], policies={adapter.collector_id: configured_policy()}, clock=lambda: NOW
    )

    result = service.collectors()

    assert result.items[0].status is MonitoringStatus.NOT_RUN
    assert result.items[0].latest_run is None
    assert result.items[0].schedule_timezone == "Asia/Seoul"


def test_due_collector_with_only_yesterday_success_is_not_run_in_overview() -> None:
    stored = make_run(
        MonitoringStatus.SUCCESS,
        started_at=NOW - timedelta(days=1),
        scheduled_date=date(2026, 9, 7),
    )
    adapter = PolicyAdapter(latest=stored)
    service = MonitoringService(
        [adapter], policies={adapter.collector_id: configured_policy()}, clock=lambda: NOW
    )

    overview = service.collectors().items[0]
    history = service.list_runs(status=MonitoringStatus.SUCCESS)

    assert overview.status is MonitoringStatus.NOT_RUN
    assert overview.latest_run is not None
    assert overview.latest_run.status is MonitoringStatus.SUCCESS
    assert history.items[0].status is MonitoringStatus.SUCCESS


def test_stale_running_is_aborted_only_in_collector_overview() -> None:
    stored = make_run(MonitoringStatus.RUNNING, started_at=NOW - timedelta(hours=2))
    adapter = PolicyAdapter(latest=stored)
    service = MonitoringService(
        [adapter], policies={adapter.collector_id: configured_policy()}, clock=lambda: NOW
    )

    overview = service.collectors().items[0]
    history = service.list_runs(status=MonitoringStatus.RUNNING)

    assert overview.status is MonitoringStatus.ABORTED
    assert overview.latest_run is not None
    assert overview.latest_run.status is MonitoringStatus.RUNNING
    assert history.items[0].status is MonitoringStatus.RUNNING


def test_stale_freshness_warns_and_keeps_check_and_change_times_distinct() -> None:
    adapter = PolicyAdapter(
        latest=make_run(MonitoringStatus.SUCCESS),
        last_successful_check_at=NOW - timedelta(minutes=10),
        latest_data_at=NOW - timedelta(hours=2),
    )
    service = MonitoringService(
        [adapter], policies={adapter.collector_id: configured_policy()}, clock=lambda: NOW
    )

    overview = service.collectors().items[0]
    freshness = service.freshness().items[0]

    assert overview.status is MonitoringStatus.WARNING
    assert overview.last_successful_check_at == NOW - timedelta(minutes=10)
    assert overview.latest_data_at == NOW - timedelta(hours=2)
    assert overview.freshness_overdue is True
    assert freshness.last_successful_check_at == NOW - timedelta(minutes=10)
    assert freshness.latest_data_at == NOW - timedelta(hours=2)
    assert freshness.freshness_sla_minutes == 60
    assert freshness.freshness_overdue is True


def test_unconfigured_policy_preserves_stored_status() -> None:
    adapter = PolicyAdapter(
        latest=make_run(MonitoringStatus.SUCCESS),
        last_successful_check_at=NOW - timedelta(days=2),
        latest_data_at=NOW - timedelta(days=2),
    )

    result = MonitoringService([adapter], clock=lambda: NOW).collectors()

    assert result.items[0].status is MonitoringStatus.SUCCESS
    assert result.items[0].schedule_timezone is None
    assert result.items[0].freshness_overdue is False


def test_summary_uses_seoul_day_boundaries_and_counts_runs_not_latest_state() -> None:
    # 2026-09-09 00:30 KST: 서울의 오늘은 UTC 15:00부터 다음날 15:00 직전이다.
    now = datetime(2026, 9, 8, 15, 30, tzinfo=UTC)
    adapter = PolicyAdapter(
        latest=make_run(MonitoringStatus.SUCCESS),
        counts={
            MonitoringStatus.SUCCESS: 1,
            MonitoringStatus.FAILED: 1,
            MonitoringStatus.RUNNING: 2,
        },
    )
    service = MonitoringService([adapter], clock=lambda: now)

    result = service.summary()

    assert result.overall_status is MonitoringStatus.FAILED
    assert result.registered_collectors == 1
    assert result.today_success_runs == 1
    assert result.today_incident_runs == 1
    assert result.running_runs == 2
    assert adapter.count_boundaries == [
        (
            datetime(2026, 9, 8, 15, tzinfo=UTC),
            datetime(2026, 9, 9, 15, tzinfo=UTC),
        )
    ]


def test_summary_includes_midnight_failure_and_later_success_but_excludes_yesterday() -> None:
    now = datetime(2026, 9, 8, 15, 30, tzinfo=UTC)

    class BoundaryAdapter(PolicyAdapter):
        def count_runs_by_status(
            self, *, started_from: datetime, started_to: datetime
        ) -> dict[MonitoringStatus, int]:
            events = [
                (datetime(2026, 9, 8, 14, 59, 59, tzinfo=UTC), MonitoringStatus.FAILED),
                (datetime(2026, 9, 8, 15, 0, tzinfo=UTC), MonitoringStatus.FAILED),
                (datetime(2026, 9, 8, 15, 10, tzinfo=UTC), MonitoringStatus.SUCCESS),
            ]
            counts: dict[MonitoringStatus, int] = {}
            for started_at, status in events:
                if started_from <= started_at < started_to:
                    counts[status] = counts.get(status, 0) + 1
            return counts

    adapter = BoundaryAdapter(latest=make_run(MonitoringStatus.SUCCESS))

    result = MonitoringService([adapter], clock=lambda: now).summary()

    assert result.today_success_runs == 1
    assert result.today_incident_runs == 1


class BrokenAdapter(PolicyAdapter):
    collector_id = "broken"
    display_name = "장애 수집기"

    def latest(self) -> CollectorRun | None:
        raise RuntimeError("private database detail")


def test_source_metadata_distinguishes_partial_total_and_zero_source_outages() -> None:
    healthy = PolicyAdapter(latest=make_run(MonitoringStatus.SUCCESS))
    broken = BrokenAdapter(latest=None)

    partial = MonitoringService([healthy, broken], clock=lambda: NOW).collectors()
    total = MonitoringService([broken], clock=lambda: NOW).collectors()
    empty = MonitoringService([], clock=lambda: NOW).collectors()

    assert partial.source_status.model_dump() == {
        "registered": 2,
        "succeeded": 1,
        "failed": 1,
        "all_sources_unavailable": False,
    }
    assert total.source_status.all_sources_unavailable is True
    assert empty.source_status.model_dump() == {
        "registered": 0,
        "succeeded": 0,
        "failed": 0,
        "all_sources_unavailable": True,
    }


class FakeThread:
    def __init__(
        self,
        *,
        target: Callable[[], None],
        name: str,
        daemon: bool,
        started_threads: list["FakeThread"],
    ) -> None:
        self.target = target
        self.name = name
        self.daemon = daemon
        self._started_threads = started_threads

    def start(self) -> None:
        # target을 실행하지 않아 영구 정지한 source를 실제 sleep 없이 모델링한다.
        self._started_threads.append(self)


def test_bounded_runner_bulkhead_keeps_healthy_source_available_across_repeated_hangs() -> None:
    started_threads: list[FakeThread] = []

    def thread_factory(**kwargs: object) -> FakeThread:
        thread = FakeThread(
            target=kwargs["target"],  # type: ignore[arg-type]
            name=kwargs["name"],  # type: ignore[arg-type]
            daemon=kwargs["daemon"],  # type: ignore[arg-type]
            started_threads=started_threads,
        )
        if thread.name.endswith("-healthy"):
            thread.start = lambda: (started_threads.append(thread), thread.target())[0]  # type: ignore[method-assign,assignment]
        return thread

    def waiter(futures: set[object], timeout: float) -> tuple[set[object], set[object]]:
        del timeout
        done = {future for future in futures if future.done()}  # type: ignore[attr-defined]
        return done, futures - done

    runner = BoundedParallelRunner(
        thread_factory=thread_factory,
        waiter=waiter,
        max_workers=1,
    )

    outcomes = [
        runner.run(
            [("healthy", lambda: "ok"), ("hung", lambda: "never")],
            timeout_seconds=1,
        )
        for _ in range(3)
    ]

    assert outcomes == [({"healthy": "ok"}, {"hung"})] * 3
    assert [thread.name for thread in started_threads].count(
        "monitoring-source-hung"
    ) == 1
    assert [thread.name for thread in started_threads].count(
        "monitoring-source-healthy"
    ) == 3
    assert all(thread.daemon for thread in started_threads)


def test_bounded_runner_returns_completed_peer_at_common_deadline() -> None:
    started_threads: list[FakeThread] = []

    def thread_factory(**kwargs: object) -> FakeThread:
        thread = FakeThread(
            target=kwargs["target"],  # type: ignore[arg-type]
            name=kwargs["name"],  # type: ignore[arg-type]
            daemon=kwargs["daemon"],  # type: ignore[arg-type]
            started_threads=started_threads,
        )
        if len(started_threads) == 0:
            thread.start = lambda: (started_threads.append(thread), thread.target())[0]  # type: ignore[method-assign,assignment]
        return thread

    def waiter(futures: set[object], timeout: float) -> tuple[set[object], set[object]]:
        del timeout
        done = {future for future in futures if future.done()}  # type: ignore[attr-defined]
        return done, futures - done

    runner = BoundedParallelRunner(
        thread_factory=thread_factory,
        waiter=waiter,
        max_workers=2,
    )

    results, failed = runner.run(
        [("healthy", lambda: "ok"), ("hung", lambda: "never")],
        timeout_seconds=1,
    )

    assert results == {"healthy": "ok"}
    assert failed == {"hung"}


def test_repeated_readiness_keeps_healthy_source_when_peer_hits_deadline() -> None:
    healthy = PolicyAdapter(latest=make_run(MonitoringStatus.SUCCESS))
    healthy.collector_id = "healthy"
    hung = PolicyAdapter(latest=None)
    hung.collector_id = "hung"

    class DeterministicDeadlineRunner:
        calls = 0

        def run(
            self,
            calls: list[tuple[str, Callable[[], Any]]],
            *,
            timeout_seconds: float,
        ) -> tuple[dict[str, Any], set[str]]:
            del timeout_seconds
            self.calls += 1
            call_by_id = dict(calls)
            return {"healthy": call_by_id["healthy"]()}, {"hung"}

    runner = DeterministicDeadlineRunner()
    service = MonitoringService([healthy, hung], runner=runner)  # type: ignore[arg-type]

    first = service.readiness()
    second = service.readiness()

    assert [item.model_dump() for item in first.items] == [
        {"collector_id": "healthy", "ready": True},
        {"collector_id": "hung", "ready": False},
    ]
    assert first.source_status.succeeded == 1
    assert second.source_status.succeeded == 1
    assert runner.calls == 2
