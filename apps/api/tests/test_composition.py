from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import monitoring_api.composition as composition
import monitoring_api.db as db
from monitoring_api.composition import build_monitoring_service
from monitoring_api.config import Settings
from monitoring_api.main import create_app


FCDAUM_CONNECTION_STRING = (
    "Driver={ODBC Driver 18 for SQL Server};Server=fcdaum-db;"
    "Database=fcdaum;UID=monitor_fcdaum;PWD=fcdaum-secret"
)
HMR_CONNECTION_STRING = (
    "Driver={ODBC Driver 18 for SQL Server};Server=hmr-db;"
    "Database=hmr;UID=monitor_hmr;PWD=hmr-secret"
)


class ReadyRepository:
    """외부 DB 없이 실제 어댑터의 readiness 계약을 실행하는 저장소다."""

    created_with: list[str] = []

    def __init__(self, connection_string: str) -> None:
        self.created_with.append(connection_string)

    def fetch_all(
        self, sql: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        del sql, parameters
        return []

    def ping(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def clear_repository_calls() -> None:
    ReadyRepository.created_with.clear()


def test_settings_loads_optional_connection_strings_as_masked_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MONITORING_FCDAUM_CONNECTION_STRING", FCDAUM_CONNECTION_STRING)
    monkeypatch.setenv("MONITORING_HMR_CONNECTION_STRING", HMR_CONNECTION_STRING)

    settings = Settings(_env_file=None)

    assert isinstance(settings.fcdaum_connection_string, SecretStr)
    assert isinstance(settings.hmr_connection_string, SecretStr)
    assert (
        settings.fcdaum_connection_string.get_secret_value()
        == FCDAUM_CONNECTION_STRING
    )
    assert settings.hmr_connection_string.get_secret_value() == HMR_CONNECTION_STRING
    rendered = f"{settings!s} {settings!r}"
    assert "fcdaum-secret" not in rendered
    assert "hmr-secret" not in rendered
    assert "**********" in rendered


def test_composition_registers_both_configured_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition, "ReadOnlyRepository", ReadyRepository)
    settings = Settings(
        fcdaum_connection_string=FCDAUM_CONNECTION_STRING,
        hmr_connection_string=HMR_CONNECTION_STRING,
        _env_file=None,
    )

    result = build_monitoring_service(settings).readiness()

    assert [item.model_dump() for item in result.items] == [
        {"collector_id": "fcdaum", "ready": True},
        {"collector_id": "hmr", "ready": True},
    ]
    assert ReadyRepository.created_with == [
        FCDAUM_CONNECTION_STRING,
        HMR_CONNECTION_STRING,
    ]


@pytest.mark.parametrize(
    ("field_name", "connection_string", "collector_id"),
    [
        ("fcdaum_connection_string", FCDAUM_CONNECTION_STRING, "fcdaum"),
        ("hmr_connection_string", HMR_CONNECTION_STRING, "hmr"),
    ],
)
def test_composition_registers_only_the_configured_source(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    connection_string: str,
    collector_id: str,
) -> None:
    monkeypatch.setattr(composition, "ReadOnlyRepository", ReadyRepository)
    settings = Settings(**{field_name: connection_string}, _env_file=None)

    result = build_monitoring_service(settings).readiness()

    assert [item.model_dump() for item in result.items] == [
        {"collector_id": collector_id, "ready": True}
    ]
    assert ReadyRepository.created_with == [connection_string]


def test_default_app_uses_composed_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition, "ReadOnlyRepository", ReadyRepository)
    settings = Settings(
        fcdaum_connection_string=FCDAUM_CONNECTION_STRING,
        _env_file=None,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "items": [{"collector_id": "fcdaum", "ready": True}],
        "errors": [],
    }


def test_default_app_without_sources_returns_clear_readiness_503() -> None:
    settings = Settings(_env_file=None)

    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "items": [],
        "errors": [
            {
                "collector_id": "configuration",
                "code": "SOURCE_UNAVAILABLE",
                "message": "등록된 모니터링 데이터 소스가 없습니다.",
            }
        ],
    }


def test_app_creation_does_not_open_a_database_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_calls: list[str] = []

    def connector(connection_string: str) -> Any:
        connector_calls.append(connection_string)
        raise AssertionError("애플리케이션 생성 중 DB에 연결하면 안 됩니다.")

    monkeypatch.setattr(db, "_default_connector", connector)
    settings = Settings(
        fcdaum_connection_string=FCDAUM_CONNECTION_STRING,
        hmr_connection_string=HMR_CONNECTION_STRING,
        _env_file=None,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert connector_calls == []


def test_invalid_connection_string_error_does_not_disclose_the_secret() -> None:
    secret = "do-not-disclose"
    settings = Settings(
        fcdaum_connection_string=f"Server=db;PWD={secret};invalid-part",
        _env_file=None,
    )

    with pytest.raises(ValueError) as raised:
        build_monitoring_service(settings)

    rendered = f"{raised.value!s} {raised.value!r}"
    assert secret not in rendered
    assert "Server=db" not in rendered
