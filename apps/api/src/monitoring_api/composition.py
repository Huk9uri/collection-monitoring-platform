"""설정에서 읽기 전용 모니터링 서비스를 조립하는 composition root다."""

from datetime import timedelta

from pydantic import SecretStr

from monitoring_api.adapters.base import CollectorAdapter
from monitoring_api.adapters.fcdaum import FcDaumAdapter
from monitoring_api.adapters.hmr import HmrAdapter
from monitoring_api.adapters.smartplace import (
    ExpectedScope,
    SmartPlaceAdapter,
    SmartPlacePolicy,
)
from monitoring_api.config import Settings
from monitoring_api.db import ReadOnlyRepository
from monitoring_api.services.monitoring import CollectorPolicy, MonitoringService


def _reveal(secret: SecretStr | None) -> str | None:
    """저장소 생성 경계에서만 연결 문자열 원문을 꺼낸다."""

    return None if secret is None else secret.get_secret_value()


def build_monitoring_service(settings: Settings) -> MonitoringService:
    """설정된 데이터 소스만 읽기 전용 어댑터로 등록한다.

    저장소 생성은 연결 문자열을 검증할 뿐 DB 연결을 열지 않는다. 실제 연결은
    HTTP 조회 또는 readiness 요청이 저장소 메서드를 호출할 때 열린다.
    """

    adapters: list[CollectorAdapter] = []
    policies: dict[str, CollectorPolicy] = {}
    if connection_string := _reveal(settings.fcdaum_connection_string):
        adapters.append(
            FcDaumAdapter(
                ReadOnlyRepository(
                    connection_string,
                    connect_timeout_seconds=settings.db_connect_timeout_seconds,
                    query_timeout_seconds=settings.db_query_timeout_seconds,
                )
            )
        )
        policies["fcdaum"] = CollectorPolicy(
            schedule_timezone=settings.fcdaum_schedule_timezone,
            daily_scheduled_time=settings.fcdaum_daily_scheduled_time,
            max_duration=(
                None
                if settings.fcdaum_max_duration_minutes is None
                else timedelta(minutes=settings.fcdaum_max_duration_minutes)
            ),
            freshness_sla={
                dataset_id: timedelta(minutes=minutes)
                for dataset_id, minutes in settings.fcdaum_freshness_sla_minutes.items()
            },
        )
    if connection_string := _reveal(settings.hmr_connection_string):
        adapters.append(
            HmrAdapter(
                ReadOnlyRepository(
                    connection_string,
                    connect_timeout_seconds=settings.db_connect_timeout_seconds,
                    query_timeout_seconds=settings.db_query_timeout_seconds,
                )
            )
        )
        policies["hmr"] = CollectorPolicy(
            schedule_timezone=settings.hmr_schedule_timezone,
            daily_scheduled_time=settings.hmr_daily_scheduled_time,
            max_duration=(
                None
                if settings.hmr_max_duration_minutes is None
                else timedelta(minutes=settings.hmr_max_duration_minutes)
            ),
            freshness_sla={
                dataset_id: timedelta(minutes=minutes)
                for dataset_id, minutes in settings.hmr_freshness_sla_minutes.items()
            },
        )
    if connection_string := _reveal(settings.smartplace_connection_string):
        smartplace_policy = None
        if settings.smartplace_schedule_timezone is not None:
            assert settings.smartplace_daily_scheduled_time is not None
            assert settings.smartplace_start_grace_minutes is not None
            assert settings.smartplace_max_duration_minutes is not None
            smartplace_policy = SmartPlacePolicy(
                schedule_timezone=settings.smartplace_schedule_timezone,
                daily_scheduled_time=settings.smartplace_daily_scheduled_time,
                start_grace=timedelta(
                    minutes=settings.smartplace_start_grace_minutes
                ),
                max_duration=timedelta(
                    minutes=settings.smartplace_max_duration_minutes
                ),
                attribution_window=timedelta(
                    minutes=(
                        settings.smartplace_schedule_attribution_window_minutes
                    )
                ),
                expected_scopes=tuple(
                    ExpectedScope(scope_id=scope_id, scope_name=scope_name)
                    for scope_id, scope_name in settings.smartplace_expected_scopes.items()
                ),
            )
        adapters.append(
            SmartPlaceAdapter(
                ReadOnlyRepository(
                    connection_string,
                    connect_timeout_seconds=settings.db_connect_timeout_seconds,
                    query_timeout_seconds=settings.db_query_timeout_seconds,
                ),
                policy=smartplace_policy,
            )
        )
    return MonitoringService(
        adapters,
        policies=policies,
        source_timeout_seconds=settings.source_timeout_seconds,
    )
