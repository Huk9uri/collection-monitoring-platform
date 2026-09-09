"""모니터링 API의 환경 설정을 제공한다."""

from datetime import time
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    Field,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_FCDAUM_DATASETS = frozenset({"reports", "issues", "missions"})
_HMR_DATASETS = frozenset(
    {
        "naver",
        "godomall",
        "coupang",
        "lotteon",
        "elevenst",
        "ssg",
        "cj_onstyle",
        "toss",
    }
)


class Settings(BaseSettings):
    """배포 환경에서 주입되는 API 설정이다."""

    cors_origins: Annotated[tuple[str, ...], NoDecode] = ()
    fcdaum_connection_string: SecretStr | None = None
    hmr_connection_string: SecretStr | None = None
    smartplace_connection_string: SecretStr | None = None
    db_connect_timeout_seconds: PositiveInt = 5
    db_query_timeout_seconds: PositiveInt = 30
    source_timeout_seconds: PositiveFloat = 35.0
    fcdaum_schedule_timezone: str | None = None
    fcdaum_daily_scheduled_time: time | None = None
    fcdaum_max_duration_minutes: PositiveInt | None = None
    fcdaum_freshness_sla_minutes: Annotated[
        dict[str, PositiveInt], NoDecode
    ] = Field(default_factory=dict)
    hmr_schedule_timezone: str | None = None
    hmr_daily_scheduled_time: time | None = None
    hmr_max_duration_minutes: PositiveInt | None = None
    hmr_freshness_sla_minutes: Annotated[
        dict[str, PositiveInt], NoDecode
    ] = Field(default_factory=dict)
    smartplace_schedule_timezone: str | None = None
    smartplace_daily_scheduled_time: time | None = None
    smartplace_start_grace_minutes: PositiveInt | None = None
    smartplace_max_duration_minutes: PositiveInt | None = None
    smartplace_expected_scopes: Annotated[
        dict[str, str], NoDecode
    ] = Field(default_factory=dict)

    model_config = SettingsConfigDict(
        env_prefix="MONITORING_",
        env_file=".env",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value

    @field_validator("cors_origins")
    @classmethod
    def require_exact_http_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        for origin in origins:
            parsed = urlsplit(origin)
            is_exact_origin = (
                parsed.scheme in {"http", "https"}
                and parsed.hostname is not None
                and parsed.username is None
                and parsed.password is None
                and not parsed.netloc.endswith(":")
                and parsed.path == ""
                and parsed.query == ""
                and parsed.fragment == ""
                and origin == f"{parsed.scheme}://{parsed.netloc}"
            )
            try:
                parsed.port
            except ValueError:
                is_exact_origin = False
            if not is_exact_origin:
                raise ValueError(
                    "CORS origin은 path가 없는 정확한 HTTP(S) origin이어야 합니다."
                )
        return origins

    @field_validator(
        "fcdaum_schedule_timezone",
        "hmr_schedule_timezone",
        "smartplace_schedule_timezone",
    )
    @classmethod
    def require_known_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("알 수 없는 수집 일정 timezone입니다.") from exc
        return value

    @field_validator(
        "fcdaum_freshness_sla_minutes",
        "hmr_freshness_sla_minutes",
        mode="before",
    )
    @classmethod
    def parse_freshness_sla(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        parsed: dict[str, int] = {}
        for entry in value.split(","):
            dataset_id, separator, minutes = entry.strip().partition("=")
            if not separator or not dataset_id or dataset_id in parsed:
                raise ValueError("신선도 SLA는 dataset=minutes 형식이어야 합니다.")
            try:
                parsed[dataset_id] = int(minutes)
            except ValueError as exc:
                raise ValueError("신선도 SLA minutes는 정수여야 합니다.") from exc
        return parsed

    @field_validator("smartplace_expected_scopes", mode="before")
    @classmethod
    def parse_smartplace_expected_scopes(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        parsed: dict[str, str] = {}
        for entry in value.split(","):
            scope_id, separator, scope_name = entry.strip().partition(":")
            scope_id = scope_id.strip()
            scope_name = scope_name.strip()
            if (
                not separator
                or not scope_id
                or not scope_name
                or scope_id in parsed
            ):
                raise ValueError(
                    "SmartPlace 예상 scope는 scope_id:표시명 형식이어야 합니다."
                )
            parsed[scope_id] = scope_name
        return parsed

    @model_validator(mode="after")
    def require_complete_collector_policies(self) -> "Settings":
        for collector_id in ("fcdaum", "hmr"):
            schedule_timezone = getattr(self, f"{collector_id}_schedule_timezone")
            scheduled_time = getattr(self, f"{collector_id}_daily_scheduled_time")
            if (schedule_timezone is None) != (scheduled_time is None):
                raise ValueError(
                    f"{collector_id} 일정 timezone과 예정 시각은 함께 설정해야 합니다."
                )

        configured_datasets = {
            "fcdaum": set(self.fcdaum_freshness_sla_minutes),
            "hmr": set(self.hmr_freshness_sla_minutes),
        }
        allowed_datasets = {
            "fcdaum": _FCDAUM_DATASETS,
            "hmr": _HMR_DATASETS,
        }
        for collector_id, datasets in configured_datasets.items():
            unknown = datasets - allowed_datasets[collector_id]
            if unknown:
                raise ValueError(
                    f"{collector_id} 알 수 없는 신선도 데이터셋: {sorted(unknown)}"
                )

        smartplace_policy_values = (
            self.smartplace_schedule_timezone,
            self.smartplace_daily_scheduled_time,
            self.smartplace_start_grace_minutes,
            self.smartplace_max_duration_minutes,
            self.smartplace_expected_scopes or None,
        )
        smartplace_is_configured = self.smartplace_connection_string is not None or any(
            value is not None for value in smartplace_policy_values
        )
        if smartplace_is_configured and any(
            value is None for value in smartplace_policy_values
        ):
            raise ValueError(
                "smartplace 일정, 시작 유예, 최대 실행시간과 예상 scope는 "
                "함께 설정해야 합니다."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """프로세스 동안 재사용할 설정 인스턴스를 반환한다."""

    return Settings()
