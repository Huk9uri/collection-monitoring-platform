"""읽기 전용 데이터 수집 모니터링 FastAPI 애플리케이션이다."""

from typing import Literal

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from monitoring_api.api.monitoring import router as monitoring_router
from monitoring_api.api.auth import router as auth_router
from monitoring_api.api.settings import router as settings_router
from monitoring_api.policy_composition import build_policy_service
from monitoring_api.auth import require_role
from monitoring_api.models import Role
from monitoring_api.control_db import ControlDatabaseUnavailable
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
    app = FastAPI(title="데이터 수집 모니터링 API",
                  docs_url=None if resolved_settings.production else '/docs',
                  redoc_url=None if resolved_settings.production else '/redoc',
                  openapi_url=None if resolved_settings.production else '/openapi.json')
    app.state.settings = resolved_settings
    app.state.monitoring_service = resolved_service
    app.state.policy_service = build_policy_service(resolved_settings, resolved_service.collector_ids)
    resolved_service.policy_service = app.state.policy_service
    if resolved_settings.production:
        app.add_middleware(HTTPSRedirectMiddleware)
    if resolved_settings.allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(resolved_settings.allowed_hosts))
    @app.exception_handler(ControlDatabaseUnavailable)
    async def control_unavailable(request: Request, exc: ControlDatabaseUnavailable):
        return JSONResponse(status_code=503, content={'detail': '제어 DB 요청을 처리할 수 없습니다.'})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Pydantic 오류의 input에 비밀번호가 포함될 수 있어 반환하지 않는다.
        return JSONResponse(status_code=422, content={'detail': '입력 값을 확인하세요.'})

    @app.middleware('http')
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.include_router(monitoring_router)
    app.include_router(auth_router)
    app.include_router(settings_router)

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    def live_health() -> HealthResponse:
        """DB 연결 없이 프로세스 생존 여부만 반환한다."""

        return HealthResponse(status="ok")

    @app.get(
        "/health/ready",
        response_model=ReadinessResponse,
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
        tags=["health"],
        dependencies=[Depends(require_role(Role.ADMIN))],
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
