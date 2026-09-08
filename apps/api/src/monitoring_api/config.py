"""모니터링 API의 환경 설정을 제공한다."""

from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """배포 환경에서 주입되는 API 설정이다."""

    cors_origins: Annotated[tuple[str, ...], NoDecode] = ()
    fcdaum_connection_string: SecretStr | None = None
    hmr_connection_string: SecretStr | None = None

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


@lru_cache
def get_settings() -> Settings:
    """프로세스 동안 재사용할 설정 인스턴스를 반환한다."""

    return Settings()
