from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import NoReturn

import pytest
from fastapi.testclient import TestClient

from monitoring_api.adapters.base import CollectorRun, FreshnessRecord
from monitoring_api.auth import CurrentUser, get_current_user
from monitoring_api.main import create_app
from monitoring_api.models import MonitoringStatus
from monitoring_api.services.monitoring import MonitoringService


class AvailableAdapter:
    collector_id = "available"
    display_name = "정상 수집기"

    def __init__(self) -> None:
        self.list_calls: list[dict[str, object]] = []

    def _run(self) -> CollectorRun:
        return CollectorRun(
            collector_id=self.collector_id,
            run_id="run-ok",
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

    def get_run(self, run_id: str) -> CollectorRun | None:
        return self._run() if run_id == "run-ok" else None

    def freshness(self) -> list[FreshnessRecord]:
        return [
            FreshnessRecord(
                collector_id=self.collector_id,
                dataset_id="orders",
                latest_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
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

    def get_run(self, run_id: str) -> CollectorRun | None:
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
                    "run_id": f"{self.collector_id}-{index}",
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
    with TestClient(create_app(monitoring_service=service)) as test_client:
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
        "detail": client.get("/api/v1/monitoring/runs/available/run-ok"),
        "freshness": client.get("/api/v1/monitoring/freshness"),
    }

    assert all(response.status_code == 200 for response in responses.values())
    assert responses["summary"].json()["items"][0]["run_id"] == "run-ok"
    assert responses["collectors"].json()["items"][0]["collector_id"] == "available"
    assert responses["runs"].json()["items"][0]["status"] == "SUCCESS"
    assert responses["detail"].json()["items"][0]["run_id"] == "run-ok"
    assert responses["freshness"].json()["items"][0]["dataset_id"] == "orders"
    assert all(response.json()["errors"] == [] for response in responses.values())


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
            "offset": 7,
            "page_size": 100,
        },
    )

    assert response.status_code == 200
    assert available_adapter.list_calls == [
        {
            "started_from": datetime(2026, 6, 7, tzinfo=UTC),
            "started_to": datetime(2026, 9, 8, tzinfo=UTC),
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
    ],
)
def test_runs_rejects_invalid_query_conditions(
    client: TestClient, params: dict[str, object]
) -> None:
    response = client.get("/api/v1/monitoring/runs", params=params)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/monitoring/runs?collector_id=unknown",
        "/api/v1/monitoring/runs/unknown/run-ok",
        "/api/v1/monitoring/freshness?collector_id=unknown",
    ],
)
def test_unknown_collector_returns_safe_404(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "수집기를 찾을 수 없습니다."}


def test_missing_run_returns_safe_404(client: TestClient) -> None:
    response = client.get("/api/v1/monitoring/runs/available/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "실행 이력을 찾을 수 없습니다."}


def test_source_failure_returns_200_partial_response_without_sensitive_details(
    client: TestClient,
) -> None:
    paths = [
        ("/api/v1/monitoring/summary", "available"),
        ("/api/v1/monitoring/collectors", "available"),
        ("/api/v1/monitoring/runs", "available"),
        ("/api/v1/monitoring/freshness", "available"),
    ]
    service = MonitoringService([AvailableAdapter(), UnavailableAdapter()])
    with use_service(client, service):
        responses = [(client.get(path), expected_id) for path, expected_id in paths]

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
        response = client.get("/api/v1/monitoring/runs/unavailable/run-ok")

    serialized = response.text.casefold()
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["errors"][0]["code"] == "SOURCE_UNAVAILABLE"
    assert "select" not in serialized
    assert "password" not in serialized
    assert "super-secret" not in serialized
    assert "private-db" not in serialized


def test_every_monitoring_route_requires_viewer_role(client: TestClient) -> None:
    paths = [
        "/api/v1/monitoring/summary",
        "/api/v1/monitoring/collectors",
        "/api/v1/monitoring/runs",
        "/api/v1/monitoring/runs/available/run-ok",
        "/api/v1/monitoring/freshness",
    ]
    client.app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        roles=frozenset()
    )
    try:
        responses = [client.get(path) for path in paths]
    finally:
        client.app.dependency_overrides.pop(get_current_user)

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


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_monitoring_routes_reject_non_get_methods(
    client: TestClient, method: str
) -> None:
    response = client.request(method, "/api/v1/monitoring/runs")

    assert response.status_code == 405
