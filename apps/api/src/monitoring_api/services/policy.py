"""DB 정책 snapshot 검증, 캐시와 주간 예정 회차 계산."""

from datetime import UTC, datetime, time, timedelta
from threading import RLock
from time import monotonic
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator

from monitoring_api.control_db import ControlDatabaseUnavailable


class Schedule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    weekday_number: int = Field(ge=1, le=7)
    scheduled_time: time
    schedule_enabled: bool = True

    @field_validator('scheduled_time')
    @classmethod
    def local_time(cls, value):
        if value.tzinfo is not None or value.microsecond:
            raise ValueError('현지 시각은 초 단위로 입력하세요.')
        return value


class MonitoringPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    timezone_name: str
    max_duration_minutes: PositiveInt | None = None
    start_grace_minutes: PositiveInt
    schedule_attribution_window_minutes: PositiveInt
    monitoring_enabled: bool = True
    schedules: list[Schedule] = Field(max_length=168)
    freshness: dict[str, PositiveInt] = Field(default_factory=dict)

    @field_validator('timezone_name')
    @classmethod
    def known_zone(cls, value):
        try:
            ZoneInfo(value)
        except (KeyError, ValueError):
            raise ValueError('유효한 IANA 시간대가 필요합니다.') from None
        return value

    @model_validator(mode='after')
    def valid_schedule(self):
        keys = [(row.weekday_number, row.scheduled_time) for row in self.schedules]
        if len(keys) != len(set(keys)):
            raise ValueError('중복 일정은 허용하지 않습니다.')
        if self.monitoring_enabled and not any(row.schedule_enabled for row in self.schedules):
            raise ValueError('활성 일정이 필요합니다.')
        if self.start_grace_minutes > self.schedule_attribution_window_minutes:
            raise ValueError('귀속 범위는 시작 유예 이상이어야 합니다.')
        return self


class PolicyUpdate(MonitoringPolicy):
    version: str | None = Field(default=None, pattern=r'^[0-9a-fA-F]{16}$')
    change_reason: str = Field(min_length=1, max_length=1000)

    @field_validator('version')
    @classmethod
    def normalize_version(cls, value):
        return value.lower() if value is not None else None

    @field_validator('change_reason')
    @classmethod
    def reason_required(cls, value):
        if not value.strip():
            raise ValueError('변경 사유가 필요합니다.')
        return value.strip()


def previous_occurrence(policy: MonitoringPolicy, now: datetime) -> datetime | None:
    if not policy.monitoring_enabled:
        return None
    zone = ZoneInfo(policy.timezone_name)
    local = now.astimezone(zone)
    candidates = []
    for day_offset in range(15):
        day = local.date() - timedelta(days=day_offset)
        for row in policy.schedules:
            if not row.schedule_enabled or row.weekday_number != day.isoweekday():
                continue
            naive = datetime.combine(day, row.scheduled_time)
            # DST 누락 시각은 건너뛰고 중복 시각은 첫 회차만 사용한다.
            candidate = naive.replace(tzinfo=zone, fold=0).astimezone(UTC)
            if candidate.astimezone(zone).replace(tzinfo=None) != naive:
                continue
            if candidate <= now:
                candidates.append(candidate)
    return max(candidates) if candidates else None


class PolicyService:
    def __init__(self, repository, fallback, datasets, *, clock=monotonic):
        self.repository = repository
        self.fallback = fallback
        self.datasets = datasets
        self.clock = clock
        self.cache = {}
        self.lock = RLock()

    def validate(self, collector_id, policy):
        if collector_id not in self.datasets:
            raise KeyError(collector_id)
        if set(policy.freshness) - set(self.datasets[collector_id]):
            raise ValueError('등록되지 않은 데이터셋입니다.')

    def get(self, collector_id):
        if collector_id not in self.datasets:
            raise KeyError(collector_id)
        with self.lock:
            cached = self.cache.get(collector_id)
            if cached and self.clock() - cached[0] < 60:
                return cached[1]
            try:
                record = self.repository.get(collector_id)
                if record is not None:
                    policy = MonitoringPolicy.model_validate(record['policy'])
                    self.validate(collector_id, policy)
                    result = {**record, 'policy_source': 'db', 'warning': None}
                else:
                    result = self._fallback(collector_id, None)
                self.cache[collector_id] = (self.clock(), result)
                return result
            except (ControlDatabaseUnavailable, ValueError):
                if cached:
                    return {**cached[1], 'policy_source': 'cached', 'warning': '정책 DB를 조회할 수 없어 마지막 정상 설정을 사용합니다.'}
                return self._fallback(collector_id, '정책 DB를 조회할 수 없어 환경 설정을 사용합니다.')

    def _fallback(self, collector_id, warning):
        policy = self.fallback.get(collector_id)
        return {'collector_id': collector_id, 'policy': (policy.model_dump(mode='json') if isinstance(policy, MonitoringPolicy) else policy),
                'version': None, 'updated_at': None, 'policy_source': 'env' if policy else 'none', 'warning': warning}

    def save(self, collector_id, update, user_id):
        self.validate(collector_id, update)
        # 이 프로세스의 저장과 조회 사이에서 오래된 캐시가 재삽입되지 않도록 한다.
        with self.lock:
            result = self.repository.save(collector_id, update, user_id)
            self.cache.pop(collector_id, None)
            return result
