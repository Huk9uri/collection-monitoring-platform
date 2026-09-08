"""수집기 어댑터가 공유하는 모델과 상태 계산 계약이다."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, Field, field_validator

from monitoring_api.models import MonitoringStatus


class CollectorAttempt(BaseModel):
    """한 브랜드 또는 채널의 단일 수집 시도다."""

    unit_id: str
    unit_name: str
    attempt_no: int
    started_at: datetime
    completed_at: datetime | None
    raw_status: str
    source_count: int
    inserted_count: int
    changed_count: int
    unchanged_count: int
    committed: bool | None = None
    error_category: str | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return require_utc_datetime(value)


class CollectorRun(BaseModel):
    """수집기별 스키마 차이를 제거한 실행 정보다."""

    collector_id: str
    run_id: str
    scheduled_date: date
    started_at: datetime
    completed_at: datetime | None
    status: MonitoringStatus
    successful_units: int
    failed_units: int
    source_count: int
    inserted_count: int
    changed_count: int
    unchanged_count: int
    attempts: list[CollectorAttempt] = Field(default_factory=list)

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return require_utc_datetime(value)


class FreshnessRecord(BaseModel):
    """고정 업무 데이터셋의 최근 적재 시각이다."""

    collector_id: str
    dataset_id: str
    latest_at: datetime | None

    @field_validator("latest_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return require_utc_datetime(value)


class CollectorAdapter(Protocol):
    """모든 수집기가 구현해야 하는 읽기 전용 조회 계약이다."""

    collector_id: str
    display_name: str

    def latest(self) -> CollectorRun | None: ...

    def list_runs(
        self,
        *,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[CollectorRun]: ...

    def get_run(self, run_id: str) -> CollectorRun | None: ...

    def freshness(self) -> list[FreshnessRecord]: ...

    def readiness(self) -> bool: ...


def require_utc_datetime(value: datetime | None) -> datetime | None:
    """공개 모델과 조회 필터가 UTC-aware 시각만 사용하도록 검증한다."""

    if value is None:
        return None
    if value.utcoffset() != timedelta(0):
        raise ValueError("시각은 UTC-aware 값이어야 합니다.")
    return value.astimezone(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """UTC로 저장된 SQL Server datetime2를 공개 UTC 시각으로 변환한다."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return require_utc_datetime(value)


def to_sql_datetime(value: datetime | None) -> datetime | None:
    """공개 시각을 UTC SQL Server datetime2 파라미터로 변환한다."""

    if value is None:
        return None
    validated = require_utc_datetime(value)
    assert validated is not None
    return validated.replace(tzinfo=None)


def map_raw_status(raw_status: str) -> MonitoringStatus:
    """수집기 원시 실행 상태를 공개 상태로 변환한다."""

    normalized = raw_status.strip().upper()
    mappings = {
        "SUCCESS": MonitoringStatus.SUCCESS,
        "SUCCESS_EMPTY": MonitoringStatus.SUCCESS_EMPTY,
        "WARNING": MonitoringStatus.WARNING,
        "PARTIAL": MonitoringStatus.PARTIAL_FAILED,
        "PARTIAL_FAILED": MonitoringStatus.PARTIAL_FAILED,
        "FAILED": MonitoringStatus.FAILED,
        "RUNNING": MonitoringStatus.RUNNING,
        "ABORTED": MonitoringStatus.ABORTED,
        "NOT_RUN": MonitoringStatus.NOT_RUN,
    }
    return mappings.get(normalized, MonitoringStatus.FAILED)


def final_attempts(attempts: list[CollectorAttempt]) -> list[CollectorAttempt]:
    """작업별 가장 큰 시도 번호만 상태와 건수 계산 대상으로 선택한다."""

    latest_by_unit: dict[str, CollectorAttempt] = {}
    for attempt in attempts:
        current = latest_by_unit.get(attempt.unit_id)
        if current is None or attempt.attempt_no > current.attempt_no:
            latest_by_unit[attempt.unit_id] = attempt
    return list(latest_by_unit.values())


def _attempt_succeeded(attempt: CollectorAttempt) -> bool:
    return (
        attempt.raw_status.upper() in {"SUCCESS", "SUCCESS_EMPTY"}
        and attempt.committed is not False
    )


def derive_run_status(
    attempts: list[CollectorAttempt], *, raw_status: str
) -> MonitoringStatus:
    """최종 시도만 사용하되 재시도 성공은 경고로 올린다."""

    mapped_raw_status = map_raw_status(raw_status)
    if mapped_raw_status in {
        MonitoringStatus.RUNNING,
        MonitoringStatus.ABORTED,
        MonitoringStatus.NOT_RUN,
    }:
        return mapped_raw_status
    if not attempts:
        return mapped_raw_status

    selected = final_attempts(attempts)
    success_count = sum(_attempt_succeeded(attempt) for attempt in selected)
    if success_count == 0:
        return MonitoringStatus.FAILED
    if success_count < len(selected):
        return MonitoringStatus.PARTIAL_FAILED

    retried = len(attempts) > len(selected) or any(
        attempt.attempt_no > 1 for attempt in selected
    )
    had_failed_attempt = any(not _attempt_succeeded(attempt) for attempt in attempts)
    if retried or had_failed_attempt:
        return MonitoringStatus.WARNING
    if all(attempt.source_count == 0 for attempt in selected):
        return MonitoringStatus.SUCCESS_EMPTY
    return MonitoringStatus.SUCCESS


def attempt_from_row(row: Mapping[str, object]) -> CollectorAttempt:
    """고정 SQL의 별칭 행을 공통 시도 모델로 변환한다."""

    return CollectorAttempt(
        unit_id=str(row["unit_id"]),
        unit_name=str(row["unit_name"]),
        attempt_no=int(row["attempt_no"]),
        started_at=as_utc(row["started_at"]),  # type: ignore[arg-type]
        completed_at=as_utc(row.get("completed_at")),  # type: ignore[arg-type]
        raw_status=str(row["raw_status"]),
        source_count=int(row.get("source_count") or 0),
        inserted_count=int(row.get("inserted_count") or 0),
        changed_count=int(row.get("changed_count") or 0),
        unchanged_count=int(row.get("unchanged_count") or 0),
        committed=None if row.get("committed") is None else bool(row["committed"]),
        error_category=(
            None if row.get("error_category") is None else str(row["error_category"])
        ),
    )


def run_from_row(
    collector_id: str,
    row: Mapping[str, object],
    attempts: list[CollectorAttempt],
) -> CollectorRun:
    """최종 시도 기준 상태와 건수를 포함한 공통 실행 모델을 만든다."""

    selected = final_attempts(attempts)
    scheduled = row["scheduled_date"]
    if isinstance(scheduled, datetime):
        scheduled = scheduled.date()
    if not isinstance(scheduled, date):
        scheduled = date.fromisoformat(str(scheduled))
    if selected:
        successful_units = sum(_attempt_succeeded(attempt) for attempt in selected)
        failed_units = len(selected) - successful_units
    else:
        successful_units = int(row.get("successful_units") or 0)
        failed_units = int(row.get("failed_units") or 0)
    return CollectorRun(
        collector_id=collector_id,
        run_id=str(row["run_id"]),
        scheduled_date=scheduled,
        started_at=as_utc(row["started_at"]),  # type: ignore[arg-type]
        completed_at=as_utc(row.get("completed_at")),  # type: ignore[arg-type]
        status=derive_run_status(attempts, raw_status=str(row["raw_status"])),
        successful_units=successful_units,
        failed_units=failed_units,
        source_count=sum(attempt.source_count for attempt in selected),
        inserted_count=sum(attempt.inserted_count for attempt in selected),
        changed_count=sum(attempt.changed_count for attempt in selected),
        unchanged_count=sum(attempt.unchanged_count for attempt in selected),
        attempts=attempts,
    )


def freshness_from_rows(
    collector_id: str, rows: list[dict[str, object]]
) -> list[FreshnessRecord]:
    return [
        FreshnessRecord(
            collector_id=collector_id,
            dataset_id=str(row["dataset_id"]),
            latest_at=as_utc(row.get("latest_at")),  # type: ignore[arg-type]
        )
        for row in rows
    ]
