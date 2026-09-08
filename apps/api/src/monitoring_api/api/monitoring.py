"""수집기 모니터링 서비스를 읽기 전용 HTTP 계약으로 노출한다."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from monitoring_api.adapters.base import CollectorRun, FreshnessRecord
from monitoring_api.auth import require_role
from monitoring_api.models import MonitoringStatus, Role
from monitoring_api.services.monitoring import (
    MonitoringService,
    RunPageResult,
    ServiceResult,
    UnknownCollectorError,
)

MAX_PAGE_SIZE = 100
MAX_OFFSET = 10_000
MAX_RUN_RANGE = timedelta(days=93)


class RunQuery(BaseModel):
    """실행 목록의 검증된 서버측 필터와 페이지 조건이다."""

    collector_id: str | None = None
    started_from: datetime | None = None
    started_to: datetime | None = None
    status: MonitoringStatus | None = None
    offset: int = Field(
        default=0,
        ge=0,
        le=MAX_OFFSET,
        description="조회 시작 위치, 최대 10,000",
    )
    page_size: int = Field(default=50, ge=1, le=MAX_PAGE_SIZE)


def get_monitoring_service(request: Request) -> MonitoringService:
    """애플리케이션 생성 시 등록된 조회 서비스를 반환한다."""

    return request.app.state.monitoring_service


MonitoringServiceDependency = Annotated[
    MonitoringService, Depends(get_monitoring_service)
]

router = APIRouter(
    prefix="/api/v1/monitoring",
    tags=["monitoring"],
    dependencies=[Depends(require_role(Role.VIEWER))],
)


def _unknown_collector() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="수집기를 찾을 수 없습니다.",
    )


def _resolve_run_range(
    started_from: datetime | None, started_to: datetime | None
) -> tuple[datetime, datetime]:
    """누락 경계를 보완해 두 끝점을 포함하는 최대 93일 UTC 범위를 만든다."""

    for value in (started_from, started_to):
        if value is not None and value.utcoffset() != timedelta(0):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="조회 시각은 UTC여야 합니다.",
            )

    try:
        if started_from is None and started_to is None:
            started_to = datetime.now(UTC)
            started_from = started_to - MAX_RUN_RANGE
        elif started_from is None:
            assert started_to is not None
            started_from = started_to - MAX_RUN_RANGE
        elif started_to is None:
            started_to = started_from + MAX_RUN_RANGE
    except OverflowError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="조회 기간이 지원되는 날짜 범위를 벗어났습니다.",
        ) from exc

    started_from = started_from.astimezone(UTC)
    started_to = started_to.astimezone(UTC)
    if started_to < started_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="조회 종료 시각은 시작 시각보다 빠를 수 없습니다.",
        )
    if started_to - started_from > MAX_RUN_RANGE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="조회 기간은 최대 93일입니다.",
        )
    return started_from, started_to


@router.get("/summary", response_model=ServiceResult[CollectorRun])
def summary(service: MonitoringServiceDependency) -> ServiceResult[CollectorRun]:
    """수집기별 최신 실행을 전체 상태 요약의 입력으로 반환한다."""

    return service.latest()


@router.get("/collectors", response_model=ServiceResult[CollectorRun])
def collectors(service: MonitoringServiceDependency) -> ServiceResult[CollectorRun]:
    """수집기별 최신 실행 상태를 반환한다."""

    return service.latest()


@router.get("/runs", response_model=RunPageResult)
def runs(
    service: MonitoringServiceDependency,
    query: Annotated[RunQuery, Query()],
) -> RunPageResult:
    """실행 이력을 제한된 기간과 페이지 크기로 조회한다."""

    started_from, started_to = _resolve_run_range(
        query.started_from, query.started_to
    )
    try:
        return service.list_runs(
            collector_id=query.collector_id,
            started_from=started_from,
            started_to=started_to,
            status=query.status,
            offset=query.offset,
            limit=query.page_size,
        )
    except UnknownCollectorError as exc:
        raise _unknown_collector() from exc


@router.get(
    "/runs/{collector_id}/{run_id}", response_model=ServiceResult[CollectorRun]
)
def run_detail(
    collector_id: str,
    run_id: str,
    service: MonitoringServiceDependency,
) -> ServiceResult[CollectorRun]:
    """등록된 수집기의 단일 실행과 전체 시도 상세를 반환한다."""

    try:
        result = service.get_run(collector_id, run_id)
    except UnknownCollectorError as exc:
        raise _unknown_collector() from exc
    if not result.items and not result.errors:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="실행 이력을 찾을 수 없습니다.",
        )
    return result


@router.get("/freshness", response_model=ServiceResult[FreshnessRecord])
def freshness(
    service: MonitoringServiceDependency,
    collector_id: Annotated[str | None, Query()] = None,
) -> ServiceResult[FreshnessRecord]:
    """수집기별 고정 데이터셋의 최신 적재 시각을 반환한다."""

    try:
        return service.freshness(collector_id=collector_id)
    except UnknownCollectorError as exc:
        raise _unknown_collector() from exc
