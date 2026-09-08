from fastapi.testclient import TestClient

from monitoring_api.config import Settings
from monitoring_api.main import create_app


def test_live_health_returns_ok_without_a_database() -> None:
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
