from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import monitoring_api.composition as composition
import monitoring_api.db as db
from monitoring_api.composition import build_monitoring_service
from monitoring_api.config import Settings
from monitoring_api.policy_composition import build_policy_service
from auth_helpers import create_admin_app as create_app


FCDAUM_CONNECTION_STRING = (
    "Driver={ODBC Driver 18 for SQL Server};Server=fcdaum-db;"
    "Database=fcdaum;UID=monitor_fcdaum;PWD=fcdaum-secret"
)
HMR_CONNECTION_STRING = (
    "Driver={ODBC Driver 18 for SQL Server};Server=hmr-db;"
    "Database=hmr;UID=monitor_hmr;PWD=hmr-secret"
)
SMARTPLACE_CONNECTION_STRING = (
    "Driver={ODBC Driver 18 for SQL Server};Server=naver-db;"
    "Database=naverDB;UID=monitor_smartplace;PWD=smartplace-secret"
)
NAVER_REVIEW_CONNECTION_STRING = (
    "Driver={ODBC Driver 18 for SQL Server};Server=naver-review-db;"
    "Database=naverDB;UID=monitor_naver_review;PWD=naver-review-secret;"
    "ApplicationIntent=ReadOnly"
)


class ReadyRepository:
    """외부 DB 없이 실제 어댑터의 readiness 계약을 실행하는 저장소다."""

    created_with: list[str] = []
    created_timeouts: list[tuple[int, int]] = []

    def __init__(
        self,
        connection_string: str,
        *,
        connect_timeout_seconds: int,
        query_timeout_seconds: int,
    ) -> None:
        self.created_with.append(connection_string)
        self.created_timeouts.append(
            (connect_timeout_seconds, query_timeout_seconds)
        )

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
    ReadyRepository.created_timeouts.clear()


def test_settings_loads_optional_connection_strings_as_masked_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MONITORING_FCDAUM_CONNECTION_STRING", FCDAUM_CONNECTION_STRING)
    monkeypatch.setenv("MONITORING_HMR_CONNECTION_STRING", HMR_CONNECTION_STRING)
    monkeypatch.setenv(
        "MONITORING_SMARTPLACE_CONNECTION_STRING", SMARTPLACE_CONNECTION_STRING
    )
    monkeypatch.setenv(
        "MONITORING_NAVER_REVIEW_CONNECTION_STRING", NAVER_REVIEW_CONNECTION_STRING
    )
    monkeypatch.setenv("MONITORING_SMARTPLACE_SCHEDULE_TIMEZONE", "Asia/Seoul")
    monkeypatch.setenv("MONITORING_SMARTPLACE_DAILY_SCHEDULED_TIME", "04:00")
    monkeypatch.setenv("MONITORING_SMARTPLACE_START_GRACE_MINUTES", "15")
    monkeypatch.setenv("MONITORING_SMARTPLACE_MAX_DURATION_MINUTES", "180")
    monkeypatch.setenv(
        "MONITORING_SMARTPLACE_EXPECTED_SCOPES",
        "hanchon:한촌설렁탕,yuksoodang:육수당",
    )

    settings = Settings(_env_file=None)

    assert isinstance(settings.fcdaum_connection_string, SecretStr)
    assert isinstance(settings.hmr_connection_string, SecretStr)
    assert isinstance(settings.smartplace_connection_string, SecretStr)
    assert isinstance(settings.naver_review_connection_string, SecretStr)
    assert (
        settings.fcdaum_connection_string.get_secret_value()
        == FCDAUM_CONNECTION_STRING
    )
    assert settings.hmr_connection_string.get_secret_value() == HMR_CONNECTION_STRING
    assert (
        settings.smartplace_connection_string.get_secret_value()
        == SMARTPLACE_CONNECTION_STRING
    )
    assert (
        settings.naver_review_connection_string.get_secret_value()
        == NAVER_REVIEW_CONNECTION_STRING
    )
    assert settings.smartplace_schedule_attribution_window_minutes == 60
    rendered = f"{settings!s} {settings!r}"
    assert "fcdaum-secret" not in rendered
    assert "hmr-secret" not in rendered
    assert "smartplace-secret" not in rendered
    assert "naver-review-secret" not in rendered
    assert "**********" in rendered


def test_naver_review_env_example_references_actual_crawler_database_key() -> None:
    env_example = Path(__file__).resolve().parents[3] / ".env.example"
    contents = env_example.read_text(encoding="utf-8")

    assert "NAVER_DB_NAME" in contents
    assert "NAVER_DB_DATABASE" not in contents


def test_one_review_connection_registers_two_collectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition, "ReadOnlyRepository", ReadyRepository)
    settings = Settings(
        naver_review_connection_string=NAVER_REVIEW_CONNECTION_STRING,
        _env_file=None,
    )

    service = build_monitoring_service(settings)

    assert set(service.collector_ids) == {
        "naver-review-visitor",
        "naver-review-blog",
    }
    assert ReadyRepository.created_with == [NAVER_REVIEW_CONNECTION_STRING]
    assert ReadyRepository.created_timeouts == [(5, 30)]


def test_review_adapters_and_policy_service_use_same_dataset_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition, "ReadOnlyRepository", ReadyRepository)
    settings = Settings(
        naver_review_connection_string=NAVER_REVIEW_CONNECTION_STRING,
        _env_file=None,
    )
    monitoring_service = build_monitoring_service(settings)
    policy_service = build_policy_service(
        settings, monitoring_service.collector_ids
    )

    actual_dataset_ids = {
        item.collector_id: item.dataset_id
        for item in monitoring_service.freshness().items
    }
    policy_dataset_ids = {
        collector_id: next(iter(dataset_ids))
        for collector_id, dataset_ids in policy_service.datasets.items()
    }

    assert actual_dataset_ids == policy_dataset_ids


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
    assert ReadyRepository.created_timeouts == [(5, 30), (5, 30)]


def test_composition_registers_smartplace_with_explicit_schedule_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition, "ReadOnlyRepository", ReadyRepository)
    settings = Settings(
        smartplace_connection_string=SMARTPLACE_CONNECTION_STRING,
        smartplace_schedule_timezone="Asia/Seoul",
        smartplace_daily_scheduled_time="04:00",
        smartplace_start_grace_minutes=15,
        smartplace_max_duration_minutes=180,
        smartplace_schedule_attribution_window_minutes=90,
        smartplace_expected_scopes="hanchon:한촌설렁탕,yuksoodang:육수당",
        _env_file=None,
    )

    result = build_monitoring_service(settings).readiness()

    assert [item.model_dump() for item in result.items] == [
        {"collector_id": "smartplace", "ready": True}
    ]
    assert settings.smartplace_expected_scopes == {
        "hanchon": "한촌설렁탕",
        "yuksoodang": "육수당",
    }
    assert settings.smartplace_schedule_attribution_window_minutes == 90
    assert ReadyRepository.created_with == [SMARTPLACE_CONNECTION_STRING]
    assert ReadyRepository.created_timeouts == [(5, 30)]


@pytest.mark.parametrize(
    "expected_scopes",
    ["hanchon", "hanchon:", ":한촌설렁탕", "hanchon:한촌,hanchon:중복"],
)
def test_settings_rejects_invalid_smartplace_expected_scopes(
    expected_scopes: str,
) -> None:
    with pytest.raises(ValueError, match="scope"):
        Settings(
            smartplace_connection_string=SMARTPLACE_CONNECTION_STRING,
            smartplace_schedule_timezone="Asia/Seoul",
            smartplace_daily_scheduled_time="04:00",
            smartplace_start_grace_minutes=15,
            smartplace_max_duration_minutes=180,
            smartplace_expected_scopes=expected_scopes,
            _env_file=None,
        )


def test_settings_requires_complete_smartplace_policy() -> None:
    with pytest.raises(ValueError, match="smartplace"):
        Settings(
            smartplace_connection_string=SMARTPLACE_CONNECTION_STRING,
            _env_file=None,
        )


@pytest.mark.parametrize("attribution_window_minutes", [5, 1500])
def test_settings_rejects_invalid_smartplace_attribution_window_relationship(
    attribution_window_minutes: int,
) -> None:
    with pytest.raises(ValueError, match="귀속 창"):
        Settings(
            smartplace_connection_string=SMARTPLACE_CONNECTION_STRING,
            smartplace_schedule_timezone="Asia/Seoul",
            smartplace_daily_scheduled_time="04:00",
            smartplace_start_grace_minutes=15,
            smartplace_max_duration_minutes=180,
            smartplace_schedule_attribution_window_minutes=(
                attribution_window_minutes
            ),
            smartplace_expected_scopes=(
                "hanchon:한촌설렁탕,yuksoodang:육수당"
            ),
            _env_file=None,
        )


@pytest.mark.parametrize("attribution_window_minutes", [15, 1439])
def test_settings_accepts_smartplace_attribution_window_boundaries(
    attribution_window_minutes: int,
) -> None:
    settings = Settings(
        smartplace_connection_string=SMARTPLACE_CONNECTION_STRING,
        smartplace_schedule_timezone="Asia/Seoul",
        smartplace_daily_scheduled_time="04:00",
        smartplace_start_grace_minutes=15,
        smartplace_max_duration_minutes=180,
        smartplace_schedule_attribution_window_minutes=attribution_window_minutes,
        smartplace_expected_scopes="hanchon:한촌설렁탕,yuksoodang:육수당",
        _env_file=None,
    )

    assert (
        settings.smartplace_schedule_attribution_window_minutes
        == attribution_window_minutes
    )


def test_composition_applies_explicit_collector_policy_and_deadlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition, "ReadOnlyRepository", ReadyRepository)
    settings = Settings(
        fcdaum_connection_string=FCDAUM_CONNECTION_STRING,
        db_connect_timeout_seconds=7,
        db_query_timeout_seconds=11,
        source_timeout_seconds=13,
        fcdaum_schedule_timezone="Asia/Seoul",
        fcdaum_daily_scheduled_time="06:30",
        fcdaum_max_duration_minutes=120,
        fcdaum_freshness_sla_minutes="reports=180,issues=240,missions=300",
        _env_file=None,
    )

    result = build_monitoring_service(settings).collectors()

    assert ReadyRepository.created_timeouts == [(7, 11)]
    assert result.items[0].schedule_timezone == "Asia/Seoul"
    assert result.items[0].daily_scheduled_time.isoformat() == "06:30:00"
    assert result.items[0].max_duration_minutes == 120
    assert settings.fcdaum_freshness_sla_minutes == {
        "reports": 180,
        "issues": 240,
        "missions": 300,
    }


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
