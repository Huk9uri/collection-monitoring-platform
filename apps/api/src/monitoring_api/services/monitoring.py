"""등록된 수집기를 제한 시간 안에서 병렬 조회하고 운영 상태를 계산한다."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future, wait
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from threading import BoundedSemaphore, Lock, Thread
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel

from monitoring_api.adapters.base import (
    CollectorAdapter,
    CollectorRun,
    FreshnessRecord,
    require_utc_datetime,
)
from monitoring_api.models import MonitoringStatus


class UnknownCollectorError(LookupError):
    """요청된 수집기가 서비스에 등록되지 않았음을 나타낸다."""


class SourceError(BaseModel):
    collector_id: str
    code: Literal["SOURCE_UNAVAILABLE"] = "SOURCE_UNAVAILABLE"
    message: str = "데이터 소스를 조회할 수 없습니다."


class SourceAvailability(BaseModel):
    """부분 장애와 전체 관측 불능을 구분하는 응답 메타데이터다."""

    registered: int
    succeeded: int
    failed: int
    all_sources_unavailable: bool


T = TypeVar("T")


class ServiceResult(BaseModel, Generic[T]):
    items: list[T]
    errors: list[SourceError]
    source_status: SourceAvailability


class RunPageResult(BaseModel):
    """필터 전체 건수와 현재 전역 페이지를 함께 반환한다."""

    items: list[CollectorRun]
    errors: list[SourceError]
    source_status: SourceAvailability
    total: int


class CollectorReadiness(BaseModel):
    collector_id: str
    ready: bool


@dataclass(frozen=True)
class CollectorPolicy:
    """저장 이력을 변경하지 않고 overview에만 적용하는 명시적 정책이다."""

    schedule_timezone: str | None = None
    daily_scheduled_time: time | None = None
    max_duration: timedelta | None = None
    freshness_sla: Mapping[str, timedelta] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.schedule_timezone is None) != (self.daily_scheduled_time is None):
            raise ValueError("일정 timezone과 예정 시각은 함께 설정해야 합니다.")
        if self.schedule_timezone is not None:
            try:
                ZoneInfo(self.schedule_timezone)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("알 수 없는 수집 일정 timezone입니다.") from exc
        if self.daily_scheduled_time is not None and self.daily_scheduled_time.tzinfo:
            raise ValueError("일일 예정 시각은 timezone 없는 현지 시각이어야 합니다.")
        if self.max_duration is not None and self.max_duration <= timedelta(0):
            raise ValueError("최대 실행 시간은 양수여야 합니다.")
        if any(sla <= timedelta(0) for sla in self.freshness_sla.values()):
            raise ValueError("신선도 SLA는 양수여야 합니다.")


class CollectorSummary(BaseModel):
    """수집기 저장 상태와 읽기 시점 정책 상태를 분리한 overview다."""

    collector_id: str
    display_name: str
    status: MonitoringStatus
    latest_run: CollectorRun | None
    schedule_timezone: str | None
    daily_scheduled_time: time | None
    max_duration_minutes: int | None
    last_successful_check_at: datetime | None
    latest_data_at: datetime | None
    freshness_overdue: bool
    freshness: list[FreshnessRecord]
    policy_source: str = 'env'
    policy_warning: str | None = None
    policy_updated_at: str | None = None


class MonitoringSummary(BaseModel):
    """Asia/Seoul 오늘 경계를 기준으로 한 명시적 KPI 계약이다."""

    overall_status: MonitoringStatus
    registered_collectors: int
    today_success_runs: int
    today_incident_runs: int
    running_runs: int
    errors: list[SourceError]
    source_status: SourceAvailability


class BoundedParallelRunner:
    """daemon 작업 수를 고정 상한으로 제한하고 공통 deadline까지만 기다린다.

    Python executor의 실행 중 thread는 취소되지 않고 프로세스 종료 시 join된다.
    따라서 작업마다 daemon thread를 사용하되 source별 bulkhead semaphore로 영구
    정지 작업까지 포함한 실행 수를 제한한다. 완료된 작업은 즉시 슬롯을 반환하고,
    deadline 뒤 실행 중인 작업은 응답을 막지 않는다. 한 source의 반복 hang이 다른
    정상 source의 슬롯을 소진하지도 않는다.
    """

    def __init__(
        self,
        *,
        thread_factory: Callable[..., Any] | None = None,
        waiter: Callable[..., tuple[set[Any], set[Any]]] = wait,
        max_workers: int = 4,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("worker 수는 양수여야 합니다.")
        self._thread_factory = thread_factory or Thread
        self._waiter = waiter
        self._max_workers = max_workers
        self._capacities: dict[str, BoundedSemaphore] = {}
        self._capacities_lock = Lock()

    def _capacity_for(self, source_id: str) -> BoundedSemaphore:
        with self._capacities_lock:
            return self._capacities.setdefault(
                source_id, BoundedSemaphore(self._max_workers)
            )

    def run(
        self,
        calls: list[tuple[str, Callable[[], T]]],
        *,
        timeout_seconds: float,
    ) -> tuple[dict[str, T], set[str]]:
        if timeout_seconds <= 0:
            raise ValueError("source timeout은 양수여야 합니다.")
        if not calls:
            return {}, set()

        future_by_id: dict[str, Future[T]] = {}
        failed: set[str] = set()
        for source_id, call in calls:
            capacity = self._capacity_for(source_id)
            if not capacity.acquire(blocking=False):
                failed.add(source_id)
                continue

            future: Future[T] = Future()
            future.set_running_or_notify_cancel()

            def execute(
                call: Callable[[], T] = call,
                future: Future[T] = future,
                capacity: BoundedSemaphore = capacity,
            ) -> None:
                try:
                    future.set_result(call())
                except BaseException as exc:
                    future.set_exception(exc)
                finally:
                    capacity.release()

            try:
                thread = self._thread_factory(
                    target=execute,
                    name=f"monitoring-source-{source_id}",
                    daemon=True,
                )
                thread.start()
            except BaseException as exc:
                future.set_exception(exc)
                capacity.release()
                failed.add(source_id)
                continue
            future_by_id[source_id] = future

        if not future_by_id:
            return {}, failed

        done, pending = self._waiter(
            set(future_by_id.values()), timeout=timeout_seconds
        )
        results: dict[str, T] = {}
        id_by_future = {future: source_id for source_id, future in future_by_id.items()}
        for future in done:
            source_id = id_by_future[future]
            try:
                results[source_id] = future.result()
            except BaseException:
                failed.add(source_id)
        failed.update(id_by_future[future] for future in pending)
        return results, failed


def _availability(registered: int, succeeded: int) -> SourceAvailability:
    failed = registered - succeeded
    return SourceAvailability(
        registered=registered,
        succeeded=succeeded,
        failed=failed,
        all_sources_unavailable=registered == 0 or succeeded == 0,
    )


def _overall_status(
    counts: Mapping[MonitoringStatus, int], *, has_source_failures: bool
) -> MonitoringStatus:
    statuses = {status for status, count in counts.items() if count > 0}
    for candidate in (
        MonitoringStatus.FAILED,
        MonitoringStatus.ABORTED,
        MonitoringStatus.PARTIAL_FAILED,
    ):
        if candidate in statuses:
            return candidate
    if has_source_failures or MonitoringStatus.WARNING in statuses:
        return MonitoringStatus.WARNING
    if MonitoringStatus.RUNNING in statuses:
        return MonitoringStatus.RUNNING
    if MonitoringStatus.NOT_RUN in statuses or not statuses:
        return MonitoringStatus.NOT_RUN
    if statuses == {MonitoringStatus.SUCCESS_EMPTY}:
        return MonitoringStatus.SUCCESS_EMPTY
    return MonitoringStatus.SUCCESS


class MonitoringService:
    """수집기 조회를 조정하며 원문 DB 예외를 외부에 노출하지 않는다."""

    def __init__(
        self,
        adapters: Iterable[CollectorAdapter],
        *,
        policies: Mapping[str, CollectorPolicy] | None = None,
        clock: Callable[[], datetime] | None = None,
        source_timeout_seconds: float = 35.0,
        runner: BoundedParallelRunner | None = None,
    ) -> None:
        if source_timeout_seconds <= 0:
            raise ValueError("source timeout은 양수여야 합니다.")
        self._adapters: dict[str, CollectorAdapter] = {}
        for adapter in adapters:
            if adapter.collector_id in self._adapters:
                raise ValueError(f"중복 수집기 ID: {adapter.collector_id}")
            self._adapters[adapter.collector_id] = adapter
        self._policies = dict(policies or {})
        unknown_policies = set(self._policies) - set(self._adapters)
        if unknown_policies:
            raise ValueError(f"등록되지 않은 수집기 정책: {sorted(unknown_policies)}")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._source_timeout_seconds = source_timeout_seconds
        self._runner = runner or BoundedParallelRunner()
        self.policy_service = None

    @property
    def collector_ids(self):
        return tuple(self._adapters)

    def _now(self) -> datetime:
        now = require_utc_datetime(self._clock())
        assert now is not None
        return now

    def _registered(self, collector_id: str) -> CollectorAdapter:
        try:
            return self._adapters[collector_id]
        except KeyError as exc:
            raise UnknownCollectorError(collector_id) from exc

    def _run_parallel(
        self,
        adapters: list[CollectorAdapter],
        operation: Callable[[CollectorAdapter], T],
    ) -> tuple[dict[str, T], list[SourceError], SourceAvailability]:
        calls = [
            (
                adapter.collector_id,
                lambda adapter=adapter: operation(adapter),
            )
            for adapter in adapters
        ]
        values, failed = self._runner.run(
            calls, timeout_seconds=self._source_timeout_seconds
        )
        errors = [
            SourceError(collector_id=adapter.collector_id)
            for adapter in adapters
            if adapter.collector_id in failed
        ]
        return values, errors, _availability(len(adapters), len(values))

    def _enrich_freshness(
        self,
        adapter: CollectorAdapter,
        *,
        now: datetime,
        last_successful_check_at: datetime | None,
        records: list[FreshnessRecord],
    ) -> list[FreshnessRecord]:
        policy = self._policies.get(adapter.collector_id, CollectorPolicy())
        snapshot = self.policy_service.get(adapter.collector_id) if self.policy_service else None
        dynamic_sla = snapshot['policy']['freshness'] if snapshot and snapshot['version'] and snapshot['policy'] else None
        monitoring_enabled = snapshot['policy']['monitoring_enabled'] if dynamic_sla is not None else True
        enriched: list[FreshnessRecord] = []
        for record in records:
            sla = (timedelta(minutes=dynamic_sla[record.dataset_id]) if record.dataset_id in dynamic_sla else None) if dynamic_sla is not None else policy.freshness_sla.get(record.dataset_id)
            overdue = bool(
                monitoring_enabled and sla is not None
                and (record.latest_data_at is None or now - record.latest_data_at > sla)
            )
            enriched.append(
                record.model_copy(
                    update={
                        "last_successful_check_at": (
                            record.last_successful_check_at
                            if record.scope_id is not None
                            else last_successful_check_at
                        ),
                        "freshness_sla_minutes": (
                            None if sla is None else int(sla.total_seconds() // 60)
                        ),
                        "freshness_overdue": overdue,
                    }
                )
            )
        return enriched

    def _collector_summary(
        self, adapter: CollectorAdapter, *, now: datetime
    ) -> CollectorSummary:
        record = self.policy_service.get(adapter.collector_id) if self.policy_service else None
        if record and record['policy'] is not None and record['version'] is not None:
            return self._controlled_summary(adapter, now, record)
        latest = adapter.latest()
        last_successful_check_at = adapter.latest_successful_check_at()
        freshness = self._enrich_freshness(
            adapter,
            now=now,
            last_successful_check_at=last_successful_check_at,
            records=adapter.freshness(),
        )
        policy = self._policies.get(adapter.collector_id, CollectorPolicy())
        data_times = [
            record.latest_data_at
            for record in freshness
            if record.latest_data_at is not None
        ]
        latest_data_at = max(data_times) if data_times else None
        freshness_overdue = any(record.freshness_overdue for record in freshness)

        effective_status = MonitoringStatus.NOT_RUN if latest is None else latest.status
        missed_schedule = False
        if (
            policy.schedule_timezone is not None
            and policy.daily_scheduled_time is not None
        ):
            timezone = ZoneInfo(policy.schedule_timezone)
            local_now = now.astimezone(timezone)
            due_at = datetime.combine(
                local_now.date(), policy.daily_scheduled_time, tzinfo=timezone
            )
            ran_for_local_day = bool(
                latest is not None and latest.scheduled_date >= local_now.date()
            )
            missed_schedule = (
                local_now >= due_at
                and not ran_for_local_day
                and (latest is None or latest.status is not MonitoringStatus.RUNNING)
            )

        if (
            latest is not None
            and latest.status is MonitoringStatus.RUNNING
            and policy.max_duration is not None
            and now - latest.started_at > policy.max_duration
        ):
            effective_status = MonitoringStatus.ABORTED
        elif missed_schedule:
            effective_status = MonitoringStatus.NOT_RUN
        elif (
            latest is not None
            and latest.status
            in {
                MonitoringStatus.SUCCESS,
                MonitoringStatus.SUCCESS_EMPTY,
                MonitoringStatus.WARNING,
            }
            and freshness_overdue
        ):
            effective_status = MonitoringStatus.WARNING

        return CollectorSummary(
            collector_id=adapter.collector_id,
            display_name=adapter.display_name,
            status=effective_status,
            latest_run=latest,
            schedule_timezone=policy.schedule_timezone,
            daily_scheduled_time=policy.daily_scheduled_time,
            max_duration_minutes=(
                None
                if policy.max_duration is None
                else int(policy.max_duration.total_seconds() // 60)
            ),
            last_successful_check_at=last_successful_check_at,
            latest_data_at=latest_data_at,
            freshness_overdue=freshness_overdue,
            freshness=freshness,
            policy_source=record['policy_source'] if record else 'env',
            policy_warning=record['warning'] if record else None,
        )

    def _controlled_summary(self, adapter, now, record):
        from monitoring_api.services.policy import MonitoringPolicy, previous_occurrence
        policy = MonitoringPolicy.model_validate(record['policy'])
        controlled = getattr(adapter, 'with_monitoring_policy', lambda policy: adapter)(policy)
        latest = controlled.latest()
        checked = controlled.latest_successful_check_at()
        freshness = []
        for item in controlled.freshness():
            sla = policy.freshness.get(item.dataset_id)
            freshness.append(item.model_copy(update={
                'last_successful_check_at': item.last_successful_check_at if item.scope_id is not None else checked,
                'freshness_sla_minutes': sla,
                'freshness_overdue': policy.monitoring_enabled and sla is not None and (item.latest_data_at is None or now - item.latest_data_at > timedelta(minutes=sla)),
            }))
        status = latest.status if latest else MonitoringStatus.NOT_RUN
        due = previous_occurrence(policy, now)
        if due and now >= due + timedelta(minutes=policy.start_grace_minutes) and not hasattr(adapter, 'with_monitoring_policy'):
            def attributed(run: CollectorRun | None) -> bool:
                # 선언한 슬롯 시각이 있으면 지연 시작을 다른 회차로 재귀속하지 않는다.
                # 시각이 없는 기존 수집기만 날짜·시작 시각 기반 귀속을 유지한다.
                if run is None or run.execution_kind not in (None, 'scheduled'):
                    return False
                if run.scheduled_at is not None:
                    return run.scheduled_at == due and due <= run.started_at < due + timedelta(minutes=policy.schedule_attribution_window_minutes)
                return bool(
                    (run.execution_kind is None or run.scheduled_date == due.astimezone(ZoneInfo(policy.timezone_name)).date())
                    and previous_occurrence(policy, run.started_at) == due
                    and run.started_at < due + timedelta(minutes=policy.schedule_attribution_window_minutes)
                )

            candidates = controlled.list_runs(started_from=due,
                started_to=min(now, due + timedelta(minutes=policy.schedule_attribution_window_minutes)), limit=1)
            candidate = candidates[0] if candidates else None
            if candidate is not None and attributed(candidate):
                latest = candidate
                status = latest.status
            if not attributed(latest):
                status = MonitoringStatus.NOT_RUN
        if policy.monitoring_enabled and latest and latest.status == MonitoringStatus.RUNNING and policy.max_duration_minutes is not None and now - latest.started_at > timedelta(minutes=policy.max_duration_minutes):
            status = MonitoringStatus.ABORTED
        overdue = any(item.freshness_overdue for item in freshness)
        if overdue and status in (MonitoringStatus.SUCCESS, MonitoringStatus.SUCCESS_EMPTY):
            status = MonitoringStatus.WARNING
        return CollectorSummary(collector_id=adapter.collector_id, display_name=adapter.display_name,
            status=status, latest_run=latest, schedule_timezone=policy.timezone_name,
            daily_scheduled_time=None, max_duration_minutes=policy.max_duration_minutes,
            last_successful_check_at=checked, latest_data_at=max((item.latest_data_at for item in freshness if item.latest_data_at), default=None),
            freshness_overdue=overdue, freshness=freshness, policy_source=record['policy_source'],
            policy_warning=record['warning'], policy_updated_at=record['updated_at'])

    def latest(self) -> ServiceResult[CollectorRun]:
        """호환용 저장 최신 실행 조회이며 동적 정책 상태를 적용하지 않는다."""

        adapters = list(self._adapters.values())
        values, errors, availability = self._run_parallel(
            adapters, lambda adapter: adapter.latest()
        )
        items = [
            values[adapter.collector_id]
            for adapter in adapters
            if values.get(adapter.collector_id) is not None
        ]
        return ServiceResult(items=items, errors=errors, source_status=availability)

    def collectors(self) -> ServiceResult[CollectorSummary]:
        now = self._now()
        adapters = list(self._adapters.values())
        values, errors, availability = self._run_parallel(
            adapters, lambda adapter: self._collector_summary(adapter, now=now)
        )
        return ServiceResult(
            items=[
                values[adapter.collector_id]
                for adapter in adapters
                if adapter.collector_id in values
            ],
            errors=errors,
            source_status=availability,
        )

    def summary(self) -> MonitoringSummary:
        now = self._now()
        seoul = ZoneInfo("Asia/Seoul")
        local_now = now.astimezone(seoul)
        local_start = datetime.combine(local_now.date(), time.min, tzinfo=seoul)
        local_end = local_start + timedelta(days=1)
        started_from = local_start.astimezone(UTC)
        started_to = local_end.astimezone(UTC)
        adapters = list(self._adapters.values())

        def load(adapter: CollectorAdapter) -> dict[MonitoringStatus, int]:
            return adapter.count_runs_by_status(
                started_from=started_from,
                started_to=started_to,
            )

        values, errors, availability = self._run_parallel(adapters, load)
        counts: dict[MonitoringStatus, int] = {}
        for source_counts in values.values():
            for run_status, count in source_counts.items():
                canonical = MonitoringStatus(run_status)
                counts[canonical] = counts.get(canonical, 0) + count

        return MonitoringSummary(
            overall_status=_overall_status(
                counts, has_source_failures=availability.failed > 0
            ),
            registered_collectors=len(adapters),
            today_success_runs=sum(
                counts.get(run_status, 0)
                for run_status in (
                    MonitoringStatus.SUCCESS,
                    MonitoringStatus.SUCCESS_EMPTY,
                )
            ),
            today_incident_runs=sum(
                counts.get(run_status, 0)
                for run_status in (
                    MonitoringStatus.PARTIAL_FAILED,
                    MonitoringStatus.FAILED,
                    MonitoringStatus.ABORTED,
                )
            ),
            running_runs=counts.get(MonitoringStatus.RUNNING, 0),
            errors=errors,
            source_status=availability,
        )

    def list_runs(
        self,
        *,
        collector_id: str | None = None,
        scope_id: str | None = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        status: MonitoringStatus | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> RunPageResult:
        adapters = (
            [self._registered(collector_id)]
            if collector_id is not None
            else list(self._adapters.values())
        )
        candidate_offset = offset if collector_id is not None else 0
        candidate_limit = limit if collector_id is not None else offset + limit
        filter_conditions: dict[str, object] = {
            "started_from": started_from,
            "started_to": started_to,
        }
        if status is not None:
            filter_conditions["status"] = status

        def load(adapter: CollectorAdapter) -> tuple[int, list[CollectorRun]]:
            conditions = dict(filter_conditions)
            if scope_id is not None:
                if not getattr(adapter, "supports_scope_filter", False):
                    return 0, []
                conditions["scope_id"] = scope_id
            total = adapter.count_runs(**conditions)
            items = adapter.list_runs(
                **conditions,
                offset=candidate_offset,
                limit=candidate_limit,
            )
            return total, items

        values, errors, availability = self._run_parallel(adapters, load)
        total = sum(value[0] for value in values.values())
        items = [run for _, runs in values.values() for run in runs]
        if collector_id is not None:
            return RunPageResult(
                items=items,
                errors=errors,
                source_status=availability,
                total=total,
            )

        ordered = sorted(
            items,
            key=lambda run: (run.started_at, run.collector_id, str(run.run_id)),
            reverse=True,
        )
        return RunPageResult(
            items=ordered[offset : offset + limit],
            errors=errors,
            source_status=availability,
            total=total,
        )

    def get_run(self, collector_id: str, run_id: UUID) -> ServiceResult[CollectorRun]:
        adapter = self._registered(collector_id)
        values, errors, availability = self._run_parallel(
            [adapter], lambda source: source.get_run(run_id)
        )
        run = values.get(collector_id)
        return ServiceResult(
            items=[] if run is None else [run],
            errors=errors,
            source_status=availability,
        )

    def freshness(
        self, *, collector_id: str | None = None
    ) -> ServiceResult[FreshnessRecord]:
        adapters = (
            [self._registered(collector_id)]
            if collector_id is not None
            else list(self._adapters.values())
        )
        now = self._now()

        def load(adapter: CollectorAdapter) -> list[FreshnessRecord]:
            last_check = adapter.latest_successful_check_at()
            return self._enrich_freshness(
                adapter,
                now=now,
                last_successful_check_at=last_check,
                records=adapter.freshness(),
            )

        values, errors, availability = self._run_parallel(adapters, load)
        items = [record for records in values.values() for record in records]
        return ServiceResult(items=items, errors=errors, source_status=availability)

    def readiness(self) -> ServiceResult[CollectorReadiness]:
        adapters = list(self._adapters.values())
        values, call_errors, _ = self._run_parallel(
            adapters, lambda adapter: adapter.readiness()
        )
        items: list[CollectorReadiness] = []
        errors_by_id = {error.collector_id: error for error in call_errors}
        ready_count = 0
        for adapter in adapters:
            ready = bool(values.get(adapter.collector_id, False))
            items.append(
                CollectorReadiness(collector_id=adapter.collector_id, ready=ready)
            )
            if ready:
                ready_count += 1
            elif adapter.collector_id not in errors_by_id:
                errors_by_id[adapter.collector_id] = SourceError(
                    collector_id=adapter.collector_id
                )
        return ServiceResult(
            items=items,
            errors=[
                errors_by_id[adapter.collector_id]
                for adapter in adapters
                if adapter.collector_id in errors_by_id
            ],
            source_status=_availability(len(adapters), ready_count),
        )
