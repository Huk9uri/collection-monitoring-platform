"""설정에서 읽기 전용 모니터링 서비스를 조립하는 composition root다."""

from pydantic import SecretStr

from monitoring_api.adapters.base import CollectorAdapter
from monitoring_api.adapters.fcdaum import FcDaumAdapter
from monitoring_api.adapters.hmr import HmrAdapter
from monitoring_api.config import Settings
from monitoring_api.db import ReadOnlyRepository
from monitoring_api.services.monitoring import MonitoringService


def _reveal(secret: SecretStr | None) -> str | None:
    """저장소 생성 경계에서만 연결 문자열 원문을 꺼낸다."""

    return None if secret is None else secret.get_secret_value()


def build_monitoring_service(settings: Settings) -> MonitoringService:
    """설정된 데이터 소스만 읽기 전용 어댑터로 등록한다.

    저장소 생성은 연결 문자열을 검증할 뿐 DB 연결을 열지 않는다. 실제 연결은
    HTTP 조회 또는 readiness 요청이 저장소 메서드를 호출할 때 열린다.
    """

    adapters: list[CollectorAdapter] = []
    if connection_string := _reveal(settings.fcdaum_connection_string):
        adapters.append(FcDaumAdapter(ReadOnlyRepository(connection_string)))
    if connection_string := _reveal(settings.hmr_connection_string):
        adapters.append(HmrAdapter(ReadOnlyRepository(connection_string)))
    return MonitoringService(adapters)
