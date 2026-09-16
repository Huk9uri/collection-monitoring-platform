from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import NoReturn
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from fastapi.testclient import TestClient

from monitoring_api.adapters.base import CollectorRun, FreshnessRecord
from monitoring_api.auth import CurrentUser, get_current_user
from monitoring_api.main import create_app
from monitoring_api.config import Settings
from monitoring_api.models import MonitoringStatus
from monitoring_api.services.monitoring import MonitoringService


RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
MISSING_RUN_ID = UUID("99999999-9999-4999-8999-999999999999")


class AvailableAdapter:
    collector_id = "available"
    display_name = "정상 수집기"

    def __init__(self) -> None:
        self.list_calls: list[dict[str, object]] = []

    def _run(self) -> CollectorRun:
        return CollectorRun(
            collector_id=self.collector_id,
            run_id=RUN_ID,
            scheduled_date=date(2026, 9, 8),
            started_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
            completed_at=datetime(2026, 9, 8, 1, 1, tzinfo=UTC),
            status=MonitoringStatus.SUCCESS,
            successful_units=1,
            failed_units=0,
            source_count=2,
            inserted_count=1,
            changed_count=0,
            unchanged_count=1,
        )

    def latest(self) -> CollectorRun | None:
        return self._run()

    def list_runs(self, **conditions: object) -> list[CollectorRun]:
        self.list_calls.append(conditions)
        return [self._run()]

    def count_runs(self, **_: object) -> int:
        return 1

    def count_runs_by_status(
        self, *, started_from: datetime, started_to: datetime
    ) -> dict[MonitoringStatus, int]:
        del started_from, started_to
        return {MonitoringStatus.SUCCESS: 1}

    def latest_successful_check_at(self) -> datetime | None:
        return datetime(2026, 9, 8, 1, 1, tzinfo=UTC)

    def get_run(self, run_id: UUID) -> CollectorRun | None:
        return self._run() if run_id == RUN_ID else None

    def freshness(self) -> list[FreshnessRecord]:
        return [
            FreshnessRecord(
                collector_id=self.collector_id,
                dataset_id="orders",
                latest_data_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
            )
        ]

    def readiness(self) -> bool:
        return True


class UnavailableAdapter(AvailableAdapter):
    collector_id = "unavailable"
    display_name = "장애 수집기"

    @staticmethod
    def _fail() -> NoReturn:
        raise RuntimeError(
            "Server=private-db;Password=super-secret; SELECT * FROM credentials"
        )

    def latest(self) -> CollectorRun | None:
        self._fail()

    def list_runs(self, **conditions: object) -> list[CollectorRun]:
        del conditions
        self._fail()

    def count_runs_by_status(
        self, *, started_from: datetime, started_to: datetime
    ) -> dict[MonitoringStatus, int]:
        del started_from, started_to
        self._fail()

    def get_run(self, run_id: UUID) -> CollectorRun | None:
        del run_id
        self._fail()

    def freshness(self) -> list[FreshnessRecord]:
        self._fail()

    def readiness(self) -> bool:
        self._fail()


class NotReadyAdapter(AvailableAdapter):
    collector_id = "not-ready"
    display_name = "준비되지 않은 수집기"

    def readiness(self) -> bool:
        return False


class ManyRunsAdapter(AvailableAdapter):
    def __init__(self, collector_id: str, minute_offset: int) -> None:
        super().__init__()
        self.collector_id = collector_id
        self.display_name = collector_id
        self.minute_offset = minute_offset

    def list_runs(self, **conditions: object) -> list[CollectorRun]:
        self.list_calls.append(conditions)
        offset = int(conditions["offset"])
        limit = int(conditions["limit"])
        base = datetime(2026, 9, 8, 12, tzinfo=UTC)
        runs = [
            self._run().model_copy(
                update={
                    "collector_id": self.collector_id,
                    "run_id": uuid5(
                        NAMESPACE_URL, f"{self.collector_id}-{index}"
                    ),
                    "started_at": base
                    - timedelta(minutes=(index * 2) + self.minute_offset),
                }
            )
            for index in range(120)
        ]
        return runs[offset : offset + limit]

    def count_runs(self, **_: object) -> int:
        return 120


@pytest.fixture(scope="module")
def available_adapter() -> AvailableAdapter:
    return AvailableAdapter()


@pytest.fixture(scope="module")
def client(available_adapter: AvailableAdapter) -> Iterator[TestClient]:
    service = MonitoringService([available_adapter])
    with TestClient(create_app(Settings(_env_file=None), monitoring_service=service)) as test_client:
        test_client.app.dependency_overrides[get_current_user] = lambda: CurrentUser(roles={'viewer'})
        yield test_client


@contextmanager
def use_service(
    client: TestClient, service: MonitoringService
) -> Iterator[TestClient]:
    previous = client.app.state.monitoring_service
    client.app.state.monitoring_service = service
    try:
        yield client
    finally:
        client.app.state.monitoring_service = previous


@pytest.fixture(autouse=True)
def clear_available_adapter_calls(available_adapter: AvailableAdapter) -> None:
    available_adapter.list_calls.clear()


def test_monitoring_get_routes_expose_service_results(client: TestClient) -> None:
    responses = {
        "summary": client.get("/api/v1/monitoring/summary"),
        "collectors": client.get("/api/v1/monitoring/collectors"),
        "runs": client.get("/api/v1/monitoring/runs"),
        "detail": client.get(f"/api/v1/monitoring/runs/available/{RUN_ID}"),
        "freshness": client.get("/api/v1/monitoring/freshness"),
    }

    assert all(response.status_code == 200 for response in responses.values())
    assert responses["summary"].json()["today_success_runs"] == 1
    assert responses["summary"].json()["registered_collectors"] == 1
    assert responses["collectors"].json()["items"][0]["collector_id"] == "available"
    assert responses["runs"].json()["items"][0]["status"] == "SUCCESS"
    assert responses["detail"].json()["items"][0]["run_id"] == str(RUN_ID)
    assert responses["freshness"].json()["items"][0]["dataset_id"] == "orders"
    assert all(response.json()["errors"] == [] for response in responses.values())


@pytest.mark.parametrize('scheduled_at', [None, datetime(2026, 9, 7, 22, tzinfo=UTC)])
def test_declared_slot_survives_collector_history_and_detail_responses(client, scheduled_at):
    class ScheduledAdapter(AvailableAdapter):
        def _run(self):
            return CollectorRun(**{**super()._run().model_dump(), 'scheduled_at': scheduled_at})

    with use_service(client, MonitoringService([ScheduledAdapter()])):
        for path in ['/api/v1/monitoring/collectors', '/api/v1/monitoring/runs',
                     f'/api/v1/monitoring/runs/available/{RUN_ID}']:
            response = client.get(path)
            assert response.status_code == 200
            item = response.json()['items'][0]
            run = item['latest_run'] if path.endswith('collectors') else item
            assert run['scheduled_at'] == (None if scheduled_at is None else '2026-09-07T22:00:00Z')


def test_runs_accepts_exact_maximum_range_and_page_size(
    client: TestClient,
    available_adapter: AvailableAdapter,
) -> None:
    response = client.get(
        "/api/v1/monitoring/runs",
        params={
            "collector_id": "available",
            "started_from": "2026-06-07T00:00:00Z",
            "started_to": "2026-09-08T00:00:00Z",
            "status": "PARTIAL_FAILED",
            "offset": 7,
            "page_size": 100,
        },
    )

    assert response.status_code == 200
    assert available_adapter.list_calls == [
        {
            "started_from": datetime(2026, 6, 7, tzinfo=UTC),
            "started_to": datetime(2026, 9, 8, tzinfo=UTC),
            "status": MonitoringStatus.PARTIAL_FAILED,
            "offset": 7,
            "limit": 100,
        }
    ]


def test_runs_without_dates_uses_a_server_utc_93_day_range(
    client: TestClient,
    available_adapter: AvailableAdapter,
) -> None:
    before = datetime.now(UTC)

    response = client.get("/api/v1/monitoring/runs")

    after = datetime.now(UTC)
    assert response.status_code == 200
    conditions = available_adapter.list_calls[-1]
    started_from = conditions["started_from"]
    started_to = conditions["started_to"]
    assert isinstance(started_from, datetime)
    assert isinstance(started_to, datetime)
    assert before <= started_to <= after
    assert started_from == started_to - timedelta(days=93)


def test_runs_accepts_maximum_offset(
    client: TestClient, available_adapter: AvailableAdapter
) -> None:
    response = client.get(
        "/api/v1/monitoring/runs",
        params={"collector_id": "available", "offset": 10_000},
    )

    assert response.status_code == 200
    assert available_adapter.list_calls[-1]["offset"] == 10_000


@pytest.mark.parametrize(
    "params,expected_from,expected_to",
    [
        (
            {"started_from": "2026-06-07T00:00:00Z"},
            datetime(2026, 6, 7, tzinfo=UTC),
            datetime(2026, 9, 8, tzinfo=UTC),
        ),
        (
            {"started_to": "2026-09-08T00:00:00Z"},
            datetime(2026, 6, 7, tzinfo=UTC),
            datetime(2026, 9, 8, tzinfo=UTC),
        ),
    ],
)
def test_runs_fills_a_missing_date_boundary_with_exactly_93_days(
    client: TestClient,
    available_adapter: AvailableAdapter,
    params: dict[str, str],
    expected_from: datetime,
    expected_to: datetime,
) -> None:
    response = client.get("/api/v1/monitoring/runs", params=params)

    assert response.status_code == 200
    conditions = available_adapter.list_calls[-1]
    assert conditions["started_from"] == expected_from
    assert conditions["started_to"] == expected_to


def test_all_collectors_runs_never_exceeds_the_global_page_size(
    client: TestClient,
) -> None:
    first = ManyRunsAdapter("first", 0)
    second = ManyRunsAdapter("second", 1)
    service = MonitoringService([first, second])
    with use_service(client, service):
        response = client.get(
            "/api/v1/monitoring/runs",
            params={
                "started_from": "2026-06-07T00:00:00Z",
                "started_to": "2026-09-08T00:00:00Z",
                "page_size": 100,
            },
        )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 100
    assert response.json()["total"] == 240


@pytest.mark.parametrize(
    "params",
    [
        {"offset": -1},
        {"offset": 10_001},
        {"page_size": 0},
        {"page_size": 101},
        {
            "started_from": "2026-06-06T00:00:00Z",
            "started_to": "2026-09-08T00:00:00Z",
        },
        {
            "started_from": "2026-09-09T00:00:00Z",
            "started_to": "2026-09-08T00:00:00Z",
        },
        {
            "started_from": "2026-09-01T09:00:00+09:00",
            "started_to": "2026-09-08T00:00:00Z",
        },
        {"status": "PARTIAL"},
        {"status": "UNKNOWN"},
    ],
)
def test_runs_rejects_invalid_query_conditions(
    client: TestClient, params: dict[str, object]
) -> None:
    response = client.get("/api/v1/monitoring/runs", params=params)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"started_from": "9999-12-31T23:59:59.999999Z"},
        {"started_to": "0001-01-01T00:00:00Z"},
    ],
)
def test_run_range_overflow_is_a_safe_422(
    client: TestClient, params: dict[str, str]
) -> None:
    response = client.get("/api/v1/monitoring/runs", params=params)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "조회 기간이 지원되는 날짜 범위를 벗어났습니다."
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/monitoring/runs?collector_id=unknown",
        f"/api/v1/monitoring/runs/unknown/{RUN_ID}",
        "/api/v1/monitoring/freshness?collector_id=unknown",
    ],
)
def test_unknown_collector_returns_safe_404(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "수집기를 찾을 수 없습니다."}


def test_missing_run_returns_safe_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/monitoring/runs/available/{MISSING_RUN_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": "실행 이력을 찾을 수 없습니다."}


def test_malformed_run_id_returns_422_before_adapter_access(client: TestClient) -> None:
    response = client.get("/api/v1/monitoring/runs/available/not-a-uuid")

    assert response.status_code == 422


def test_source_failure_returns_200_partial_response_without_sensitive_details(
    client: TestClient,
) -> None:
    paths = [
        ("/api/v1/monitoring/collectors", "available"),
        ("/api/v1/monitoring/runs", "available"),
        ("/api/v1/monitoring/freshness", "available"),
    ]
    service = MonitoringService([AvailableAdapter(), UnavailableAdapter()])
    with use_service(client, service):
        summary_response = client.get("/api/v1/monitoring/summary")
        responses = [(client.get(path), expected_id) for path, expected_id in paths]

    assert summary_response.status_code == 200
    assert summary_response.json()["source_status"] == {
        "registered": 2,
        "succeeded": 1,
        "failed": 1,
        "all_sources_unavailable": False,
    }
    assert summary_response.json()["errors"][0]["collector_id"] == "unavailable"

    for response, expected_id in responses:
        body = response.json()
        serialized = response.text.casefold()
        assert response.status_code == 200
        assert body["items"][0]["collector_id"] == expected_id
        assert body["errors"] == [
            {
                "collector_id": "unavailable",
                "code": "SOURCE_UNAVAILABLE",
                "message": "데이터 소스를 조회할 수 없습니다.",
            }
        ]
        assert "select" not in serialized
        assert "password" not in serialized
        assert "super-secret" not in serialized
        assert "private-db" not in serialized


def test_run_detail_source_failure_returns_safe_200_error(client: TestClient) -> None:
    service = MonitoringService([UnavailableAdapter()])
    with use_service(client, service):
        response = client.get(f"/api/v1/monitoring/runs/unavailable/{RUN_ID}")

    serialized = response.text.casefold()
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["errors"][0]["code"] == "SOURCE_UNAVAILABLE"
    assert "select" not in serialized
    assert "password" not in serialized
    assert "super-secret" not in serialized
    assert "private-db" not in serialized


@pytest.mark.parametrize(
    "service",
    [MonitoringService([UnavailableAdapter()]), MonitoringService([])],
)
def test_collectors_exposes_total_source_unavailability(
    client: TestClient, service: MonitoringService
) -> None:
    with use_service(client, service):
        response = client.get("/api/v1/monitoring/collectors")

    assert response.status_code == 200
    assert response.json()["source_status"]["all_sources_unavailable"] is True
    assert response.json()["source_status"]["succeeded"] == 0


def test_every_monitoring_route_requires_viewer_role(client: TestClient) -> None:
    paths = [
        "/api/v1/monitoring/summary",
        "/api/v1/monitoring/collectors",
        "/api/v1/monitoring/runs",
        f"/api/v1/monitoring/runs/available/{RUN_ID}",
        "/api/v1/monitoring/freshness",
    ]
    client.app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        roles=frozenset()
    )
    try:
        responses = [client.get(path) for path in paths]
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: CurrentUser(roles={'viewer'})

    assert all(response.status_code == 403 for response in responses)
    assert all(
        response.json() == {"detail": "권한이 없습니다."} for response in responses
    )


def test_monitoring_openapi_declares_only_get_operations() -> None:
    schema = create_app(
        monitoring_service=MonitoringService([AvailableAdapter()])
    ).openapi()
    monitoring_paths = {
        path: operations
        for path, operations in schema["paths"].items()
        if path.startswith("/api/v1/monitoring/")
    }

    assert set(monitoring_paths) == {
        "/api/v1/monitoring/summary",
        "/api/v1/monitoring/collectors",
        "/api/v1/monitoring/runs",
        "/api/v1/monitoring/runs/{collector_id}/{run_id}",
        "/api/v1/monitoring/freshness",
    }
    assert all(set(operations) == {"get"} for operations in monitoring_paths.values())
    run_parameters = monitoring_paths["/api/v1/monitoring/runs"]["get"]["parameters"]
    offset_parameter = next(
        parameter for parameter in run_parameters if parameter["name"] == "offset"
    )
    assert offset_parameter["schema"]["maximum"] == 10_000
    assert "최대 10,000" in offset_parameter["description"]
    status_parameter = next(
        parameter for parameter in run_parameters if parameter["name"] == "status"
    )
    assert status_parameter["schema"]["anyOf"][0]["$ref"].endswith(
        "/MonitoringStatus"
    )
    detail_parameters = monitoring_paths[
        "/api/v1/monitoring/runs/{collector_id}/{run_id}"
    ]["get"]["parameters"]
    run_id_parameter = next(
        parameter for parameter in detail_parameters if parameter["name"] == "run_id"
    )
    assert run_id_parameter["schema"]["format"] == "uuid"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_monitoring_routes_reject_non_get_methods(
    client: TestClient, method: str
) -> None:
    response = client.request(method, "/api/v1/monitoring/runs")

    assert response.status_code == 405
