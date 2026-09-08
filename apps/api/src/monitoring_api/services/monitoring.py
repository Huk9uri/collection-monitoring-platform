"""등록된 수집기만 조회하고 소스 장애를 부분 응답으로 격리한다."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

from monitoring_api.adapters.base import (
    CollectorAdapter,
    CollectorRun,
    FreshnessRecord,
)
from monitoring_api.models import MonitoringStatus


class UnknownCollectorError(LookupError):
    """요청된 수집기가 서비스에 등록되지 않았음을 나타낸다."""


class SourceError(BaseModel):
    collector_id: str
    code: Literal["SOURCE_UNAVAILABLE"] = "SOURCE_UNAVAILABLE"
    message: str = "데이터 소스를 조회할 수 없습니다."


T = TypeVar("T")


class ServiceResult(BaseModel, Generic[T]):
    items: list[T]
    errors: list[SourceError]


class RunPageResult(BaseModel):
    """필터 전체 건수와 현재 전역 페이지를 함께 반환한다."""

    items: list[CollectorRun]
    errors: list[SourceError]
    total: int


class CollectorReadiness(BaseModel):
    collector_id: str
    ready: bool


class MonitoringService:
    """수집기 조회를 조정하며 원문 DB 예외를 외부에 노출하지 않는다."""

    def __init__(self, adapters: Iterable[CollectorAdapter]) -> None:
        self._adapters: dict[str, CollectorAdapter] = {}
        for adapter in adapters:
            if adapter.collector_id in self._adapters:
                raise ValueError(f"중복 수집기 ID: {adapter.collector_id}")
            self._adapters[adapter.collector_id] = adapter

    def _registered(self, collector_id: str) -> CollectorAdapter:
        try:
            return self._adapters[collector_id]
        except KeyError as exc:
            raise UnknownCollectorError(collector_id) from exc

    def _collect_many(
        self,
        operation: Callable[[CollectorAdapter], list[T]],
        *,
        collector_id: str | None = None,
    ) -> ServiceResult[T]:
        adapters = (
            [self._registered(collector_id)]
            if collector_id is not None
            else list(self._adapters.values())
        )
        items: list[T] = []
        errors: list[SourceError] = []
        for adapter in adapters:
            try:
                items.extend(operation(adapter))
            except Exception:
                errors.append(SourceError(collector_id=adapter.collector_id))
        return ServiceResult(items=items, errors=errors)

    def latest(self) -> ServiceResult[CollectorRun]:
        def load(adapter: CollectorAdapter) -> list[CollectorRun]:
            run = adapter.latest()
            return [] if run is None else [run]

        return self._collect_many(load)

    def list_runs(
        self,
        *,
        collector_id: str | None = None,
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
        items: list[CollectorRun] = []
        errors: list[SourceError] = []
        total = 0
        filter_conditions: dict[str, object] = {
            "started_from": started_from,
            "started_to": started_to,
        }
        if status is not None:
            filter_conditions["status"] = status
        for adapter in adapters:
            try:
                adapter_total = adapter.count_runs(**filter_conditions)
                adapter_items = adapter.list_runs(
                    **filter_conditions,
                    offset=candidate_offset,
                    limit=candidate_limit,
                )
            except Exception:
                errors.append(SourceError(collector_id=adapter.collector_id))
                continue
            total += adapter_total
            items.extend(adapter_items)

        if collector_id is not None:
            return RunPageResult(items=items, errors=errors, total=total)

        ordered = sorted(
            items,
            key=lambda run: (run.started_at, run.collector_id, run.run_id),
            reverse=True,
        )
        return RunPageResult(
            items=ordered[offset : offset + limit],
            errors=errors,
            total=total,
        )

    def get_run(self, collector_id: str, run_id: str) -> ServiceResult[CollectorRun]:
        adapter = self._registered(collector_id)
        try:
            run = adapter.get_run(run_id)
        except Exception:
            return ServiceResult(
                items=[], errors=[SourceError(collector_id=collector_id)]
            )
        return ServiceResult(items=[] if run is None else [run], errors=[])

    def freshness(
        self, *, collector_id: str | None = None
    ) -> ServiceResult[FreshnessRecord]:
        return self._collect_many(
            lambda adapter: adapter.freshness(), collector_id=collector_id
        )

    def readiness(self) -> ServiceResult[CollectorReadiness]:
        items: list[CollectorReadiness] = []
        errors: list[SourceError] = []
        for adapter in self._adapters.values():
            try:
                ready = adapter.readiness()
                items.append(
                    CollectorReadiness(
                        collector_id=adapter.collector_id,
                        ready=ready,
                    )
                )
                if not ready:
                    errors.append(SourceError(collector_id=adapter.collector_id))
            except Exception:
                items.append(
                    CollectorReadiness(
                        collector_id=adapter.collector_id,
                        ready=False,
                    )
                )
                errors.append(SourceError(collector_id=adapter.collector_id))
        return ServiceResult(items=items, errors=errors)
