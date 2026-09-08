from pathlib import Path

from fastapi.testclient import TestClient

from monitoring_api.config import Settings, get_settings
from monitoring_api.main import create_app


def test_live_health_returns_ok_without_a_database() -> None:
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
