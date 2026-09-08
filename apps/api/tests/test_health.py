from pathlib import Path
import tomllib

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from monitoring_api.config import Settings, get_settings
from monitoring_api.main import create_app
from monitoring_api.services.monitoring import MonitoringService

from test_monitoring_api import AvailableAdapter, NotReadyAdapter, UnavailableAdapter


def test_live_health_returns_ok_without_a_database() -> None:
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_health_returns_ok_when_every_adapter_is_ready() -> None:
    service = MonitoringService([AvailableAdapter()])
    with TestClient(create_app(monitoring_service=service)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "items": [{"collector_id": "available", "ready": True}],
        "errors": [],
    }


def test_ready_health_returns_503_when_an_adapter_reports_not_ready() -> None:
    service = MonitoringService([AvailableAdapter(), NotReadyAdapter()])
    with TestClient(create_app(monitoring_service=service)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["items"][-1] == {
        "collector_id": "not-ready",
        "ready": False,
    }
    assert response.json()["errors"][-1]["code"] == "SOURCE_UNAVAILABLE"


def test_ready_health_returns_safe_503_when_an_adapter_is_not_ready() -> None:
    service = MonitoringService([AvailableAdapter(), UnavailableAdapter()])
    with TestClient(create_app(monitoring_service=service)) as client:
        response = client.get("/health/ready")

    body = response.json()
    serialized = response.text.casefold()
    assert response.status_code == 503
    assert body == {
        "status": "unavailable",
        "items": [
            {"collector_id": "available", "ready": True},
            {"collector_id": "unavailable", "ready": False},
        ],
        "errors": [
            {
                "collector_id": "unavailable",
                "code": "SOURCE_UNAVAILABLE",
                "message": "데이터 소스를 조회할 수 없습니다.",
            }
        ],
    }
    assert "select" not in serialized
    assert "password" not in serialized
    assert "super-secret" not in serialized
    assert "private-db" not in serialized


def test_settings_loads_plain_cors_origin_from_example_env_file() -> None:
    env_example = Path(__file__).resolve().parents[3] / ".env.example"

    settings = Settings(_env_file=env_example)

    assert settings.cors_origins == ("http://localhost:5173",)


def test_create_app_loads_plain_cors_origin_from_environment(monkeypatch) -> None:
    origin = "https://monitoring.example.internal"
    monkeypatch.setenv("MONITORING_CORS_ORIGINS", origin)
    get_settings.cache_clear()
    try:
        settings = Settings()
        client = TestClient(create_app())

        response = client.options(
            "/health/live",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )

        assert settings.cors_origins == (origin,)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
    finally:
        get_settings.cache_clear()


def test_cors_allows_only_the_configured_origin_get_and_authorization_header() -> None:
    origin = "https://monitoring.example.internal"
    client = TestClient(create_app(Settings(cors_origins=(origin,))))

    response = client.options(
        "/health/live",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-methods"] == "GET"
    assert "Authorization" in response.headers["access-control-allow-headers"]
    assert "X-API-Key" not in response.headers["access-control-allow-headers"]


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "monitoring.example.internal",
        "ftp://monitoring.example.internal",
        "https://user@monitoring.example.internal",
        "https://monitoring.example.internal:",
        "https://monitoring.example.internal/path",
        "https://monitoring.example.internal?debug=true",
        "https://monitoring.example.internal#fragment",
    ],
)
def test_settings_rejects_non_exact_http_cors_origins(origin: str) -> None:
    with pytest.raises(ValidationError, match="CORS"):
        Settings(cors_origins=(origin,), _env_file=None)


@pytest.mark.parametrize(
    "field_name",
    [
        "db_connect_timeout_seconds",
        "db_query_timeout_seconds",
        "source_timeout_seconds",
    ],
)
def test_settings_requires_positive_timeouts(field_name: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field_name: 0}, _env_file=None)


@pytest.mark.parametrize(
    "values",
    [
        {"fcdaum_schedule_timezone": "Asia/Seoul"},
        {"fcdaum_daily_scheduled_time": "10:00"},
        {"hmr_schedule_timezone": "Asia/Seoul"},
        {"hmr_daily_scheduled_time": "10:00"},
    ],
)
def test_settings_requires_schedule_timezone_and_time_as_a_pair(
    values: dict[str, str],
) -> None:
    with pytest.raises(ValidationError, match="함께"):
        Settings(**values, _env_file=None)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("fcdaum_freshness_sla_minutes", "unknown=60"),
        ("hmr_freshness_sla_minutes", "unknown=60"),
    ],
)
def test_settings_rejects_unknown_freshness_dataset(
    field_name: str, value: str
) -> None:
    with pytest.raises(ValidationError, match="데이터셋"):
        Settings(**{field_name: value}, _env_file=None)


def test_api_declares_tzdata_for_windows_zoneinfo() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    dependencies = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]

    assert any(dependency.startswith("tzdata") for dependency in dependencies)


def test_cors_rejects_unconfigured_origin_and_non_get_method() -> None:
    origin = "https://monitoring.example.internal"
    client = TestClient(create_app(Settings(cors_origins=(origin,))))

    unconfigured_origin_response = client.options(
        "/health/live",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    post_response = client.options(
        "/health/live",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    unsupported_header_response = client.options(
        "/health/live",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )

    assert unconfigured_origin_response.status_code == 400
    assert "access-control-allow-origin" not in unconfigured_origin_response.headers
    assert post_response.status_code == 400
    assert unsupported_header_response.status_code == 400
