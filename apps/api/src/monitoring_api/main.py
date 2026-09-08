"""읽기 전용 데이터 수집 모니터링 FastAPI 애플리케이션이다."""

from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from monitoring_api.config import Settings, get_settings


class HealthResponse(BaseModel):
    """라이브 상태 확인 응답이다."""

    status: Literal["ok"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """설정된 CORS 경계를 가진 FastAPI 애플리케이션을 생성한다."""

    resolved_settings = settings or get_settings()
    app = FastAPI(title="데이터 수집 모니터링 API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization"],
    )

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    def live_health() -> HealthResponse:
        """DB 연결 없이 프로세스 생존 여부만 반환한다."""

        return HealthResponse(status="ok")

    return app


app = create_app()
