"""수집기와 HTTP API가 공유하는 공통 모델을 정의한다."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, field_validator, model_validator


class MonitoringStatus(StrEnum):
    """수집 실행 결과를 표현하는 공개 상태 계약이다."""

    SUCCESS = "SUCCESS"
    SUCCESS_EMPTY = "SUCCESS_EMPTY"
    WARNING = "WARNING"
    PARTIAL_FAILED = "PARTIAL_FAILED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    ABORTED = "ABORTED"
    NOT_RUN = "NOT_RUN"


class StatusSeverity(StrEnum):
    """운영 화면에서 상태를 분류할 심각도다."""

    HEALTHY = "healthy"
    WARNING = "warning"
    INCIDENT = "incident"
    UNKNOWN = "unknown"


class Role(StrEnum):
    """현재와 향후 인증 공급자가 사용할 역할이다."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


_STATUS_SEVERITIES = {
    MonitoringStatus.SUCCESS: StatusSeverity.HEALTHY,
    MonitoringStatus.SUCCESS_EMPTY: StatusSeverity.HEALTHY,
    MonitoringStatus.WARNING: StatusSeverity.WARNING,
    MonitoringStatus.PARTIAL_FAILED: StatusSeverity.INCIDENT,
    MonitoringStatus.FAILED: StatusSeverity.INCIDENT,
    MonitoringStatus.RUNNING: StatusSeverity.UNKNOWN,
    MonitoringStatus.ABORTED: StatusSeverity.INCIDENT,
    MonitoringStatus.NOT_RUN: StatusSeverity.UNKNOWN,
}


def status_severity(status: MonitoringStatus) -> StatusSeverity:
    """공개 상태를 운영용 심각도로 변환한다."""

    return _STATUS_SEVERITIES[status]


class RunTimeRange(BaseModel):
    """API가 UTC로만 노출하는 수집 실행 시각 범위다."""

    started_at: datetime
    completed_at: datetime | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.utcoffset() != timedelta(0):
            raise ValueError("시각은 UTC여야 합니다.")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_time_order(self) -> "RunTimeRange":
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("완료 시각은 시작 시각보다 빠를 수 없습니다.")
        return self
