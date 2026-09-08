"""읽기 전용 데이터 수집 모니터링 FastAPI 애플리케이션이다."""

from typing import Literal

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from monitoring_api.api.monitoring import router as monitoring_router
from monitoring_api.composition import build_monitoring_service
from monitoring_api.config import Settings, get_settings
from monitoring_api.services.monitoring import (
    CollectorReadiness,
    MonitoringService,
    SourceError,
)


class HealthResponse(BaseModel):
    """라이브 상태 확인 응답이다."""

    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    """모든 등록 수집기의 준비 상태와 안전한 오류를 반환한다."""

    status: Literal["ok", "unavailable"]
    items: list[CollectorReadiness] = Field(default_factory=list)
    errors: list[SourceError] = Field(default_factory=list)


def create_app(
    settings: Settings | None = None,
    *,
    monitoring_service: MonitoringService | None = None,
) -> FastAPI:
    """설정된 CORS 경계를 가진 FastAPI 애플리케이션을 생성한다."""

    resolved_settings = settings or get_settings()
    resolved_service = monitoring_service or build_monitoring_service(
        resolved_settings
    )
    app = FastAPI(title="데이터 수집 모니터링 API")
    app.state.monitoring_service = resolved_service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization"],
    )
    app.include_router(monitoring_router)

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    def live_health() -> HealthResponse:
        """DB 연결 없이 프로세스 생존 여부만 반환한다."""

        return HealthResponse(status="ok")

    @app.get(
        "/health/ready",
        response_model=ReadinessResponse,
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
        tags=["health"],
    )
    def ready_health(response: Response) -> ReadinessResponse:
        """등록된 모든 데이터 소스가 조회 가능한지 반환한다."""

        result = resolved_service.readiness()
        is_ready = bool(result.items) and all(item.ready for item in result.items)
        errors = result.errors
        if not result.items:
            errors = [
                SourceError(
                    collector_id="configuration",
                    message="등록된 모니터링 데이터 소스가 없습니다.",
                )
            ]
        if not is_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="ok" if is_ready else "unavailable",
            items=result.items,
            errors=errors,
        )

    return app


app = create_app()
