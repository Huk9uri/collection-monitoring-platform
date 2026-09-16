"""네이버 리뷰 고정 SELECT를 메모리 DB에서 실행해 조회 계약을 검증한다."""

from datetime import UTC, date, datetime, timedelta, timezone
import sqlite3
import re
from uuid import UUID

import pytest
from sqlglot import transpile

from monitoring_api.adapters.naver_review import NaverReviewAdapter
from monitoring_api.db import ReadOnlyRepository
from monitoring_api.models import MonitoringStatus


RUN = UUID("00000000-0000-0000-0000-000000000001")
OTHER = UUID("00000000-0000-0000-0000-000000000002")
START = datetime(2026, 9, 15, 22, tzinfo=UTC)
END = datetime(2026, 9, 16, 22, tzinfo=UTC)


class Repository:
    """외부 SQL Server 없이 실제 쿼리의 필터·정렬·집계를 실행한다."""

    def __init__(self):
        self.calls = []
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("ATTACH DATABASE ':memory:' AS dbo")
        self.db.executescript("""
            CREATE TABLE dbo.NAVER_REVIEW_COLLECTION_RUN (
                RunId TEXT, ReviewKind TEXT, ExecutionKind TEXT, TargetKind TEXT,
                ScheduledAt TEXT, StartedAt TEXT, CompletedAt TEXT, Status TEXT,
                TargetStoreCount INTEGER, SuccessfulStoreCount INTEGER,
                FailedStoreCount INTEGER, SourceCount INTEGER, InsertedCount INTEGER,
                TargetDateFrom TEXT, TargetDateTo TEXT, TargetPlaceId TEXT
            );
            CREATE TABLE dbo.NAVER_REVIEW_COLLECTION_ATTEMPT (
                RunId TEXT, PlaceId TEXT, AttemptNo INTEGER, BrandCode TEXT,
                BrandName TEXT, StoreName TEXT, StartedAt TEXT, CompletedAt TEXT,
                Status TEXT, SourceCount INTEGER, InsertedCount INTEGER,
                Committed INTEGER, ErrorCategory TEXT
            );
            CREATE TABLE dbo.naver_review_visitor (date TEXT);
            CREATE TABLE dbo.naver_review_blog (date TEXT);
        """)

    def run(self, run_id=RUN, kind="visitor", execution="scheduled", **changes):
        values = dict(
            RunId=str(run_id), ReviewKind=kind, ExecutionKind=execution,
            TargetKind="all-stores",
            ScheduledAt="2026-09-15 22:00:00" if execution == "scheduled" else None,
            StartedAt="2026-09-15 22:01:00", CompletedAt="2026-09-15 22:10:00",
            Status="SUCCESS", TargetStoreCount=1, SuccessfulStoreCount=1,
            FailedStoreCount=0, SourceCount=3, InsertedCount=2,
            TargetDateFrom=None, TargetDateTo=None, TargetPlaceId=None,
        )
        values.update(changes)
        self.db.execute(
            f"INSERT INTO dbo.NAVER_REVIEW_COLLECTION_RUN ({','.join(values)}) "
            f"VALUES ({','.join('?' for _ in values)})", tuple(values.values()),
        )

    def attempt(self, run_id=RUN, **changes):
        values = dict(
            RunId=str(run_id), PlaceId="123", AttemptNo=1, BrandCode="001",
            BrandName="한촌설렁탕", StoreName="테스트점",
            StartedAt="2026-09-15 22:01:00", CompletedAt="2026-09-15 22:10:00",
            Status="SUCCESS", SourceCount=3, InsertedCount=2, Committed=1,
            ErrorCategory=None,
        )
        values.update(changes)
        self.db.execute(
            f"INSERT INTO dbo.NAVER_REVIEW_COLLECTION_ATTEMPT ({','.join(values)}) "
            f"VALUES ({','.join('?' for _ in values)})", tuple(values.values()),
        )

    def fetch_all(self, sql, parameters=()):
        ReadOnlyRepository._validate_select(sql)
        self.calls.append((sql, parameters))
        # T-SQL OFFSET/FETCH가 SQLite LIMIT/OFFSET으로 바뀌어도 바인딩 순서를 보존한다.
        positions = iter(range(len(parameters)))
        named = re.sub(r"\?", lambda _: f"@p{next(positions)}", sql)
        translated = transpile(named, read="tsql", write="sqlite")[0]
        parameters = {
            f"p{index}": value.isoformat(sep=" ") if isinstance(value, datetime) else value
            for index, value in enumerate(parameters)
        }
        rows = [dict(row) for row in self.db.execute(translated, parameters)]
        for row in rows:
            for key, value in row.items():
                if value is not None and key.endswith("_at"):
                    row[key] = datetime.fromisoformat(value)
                elif value is not None and key in {"target_date_from", "target_date_to"}:
                    row[key] = date.fromisoformat(value)
        return rows

    def ping(self):
        return True


@pytest.fixture
def repo():
    repository = Repository()
    yield repository
    repository.db.close()


def test_latest_ignores_newer_manual_success_after_scheduled_failure(repo):
    repo.run(Status="FAILED", SuccessfulStoreCount=0, FailedStoreCount=1)
    repo.run(OTHER, execution="manual", StartedAt="2026-09-16 02:00:00")
    latest = NaverReviewAdapter(repo, review_kind="visitor").latest()
    assert latest.run_id == RUN
    assert latest.status == MonitoringStatus.FAILED
    assert latest.scheduled_date == date(2026, 9, 16)
    assert latest.started_at == datetime(2026, 9, 15, 22, 1, tzinfo=UTC)


def test_declared_slot_is_preserved_in_latest_history_and_detail(repo):
    repo.run(StartedAt='2026-09-15 23:05:00')
    repo.run(OTHER, execution='manual')
    adapter = NaverReviewAdapter(repo, review_kind='visitor')
    for run in [adapter.latest(), adapter.list_runs()[0], adapter.get_run(RUN)]:
        assert run.model_dump(mode='json')['scheduled_at'] == '2026-09-15T22:00:00Z'
    assert adapter.get_run(OTHER).model_dump()['scheduled_at'] is None


@pytest.mark.parametrize("kind,other", [("visitor", "blog"), ("blog", "visitor")])
def test_review_kinds_are_isolated_in_every_run_query(repo, kind, other):
    repo.run(kind=kind)
    repo.run(OTHER, kind=other, StartedAt="2026-09-16 02:00:00")
    adapter = NaverReviewAdapter(repo, review_kind=kind)
    assert adapter.collector_id == f"naver-review-{kind}"
    assert [run.run_id for run in adapter.list_runs()] == [RUN]
    assert adapter.count_runs() == 1
    assert adapter.latest().run_id == RUN
    assert adapter.get_run(OTHER) is None
    assert adapter.get_run(RUN).run_id == RUN
    assert adapter.count_runs_by_status(started_from=START, started_to=END) == {
        MonitoringStatus.SUCCESS: 1,
    }
    assert adapter.latest_successful_check_at() == datetime(2026, 9, 15, 22, 10, tzinfo=UTC)
    assert all(parameters[0] == kind for _, parameters in repo.calls)


@pytest.mark.parametrize("execution", ["scheduled", "manual", "backfill"])
def test_history_detail_preserve_execution_target_and_run_metrics(repo, execution):
    repo.run(execution=execution, TargetKind="date-range",
             TargetDateFrom="2026-01-01", TargetDateTo="2026-09-16",
             SourceCount=8, InsertedCount=5)
    adapter = NaverReviewAdapter(repo, review_kind="visitor")
    listed = adapter.list_runs()[0]
    detailed = adapter.get_run(RUN)
    assert listed.model_dump() == detailed.model_dump()
    assert (listed.execution_kind, listed.target_kind) == (execution, "date-range")
    assert listed.target_date_from == date(2026, 1, 1)
    assert listed.target_date_to == date(2026, 9, 16)
    assert (listed.source_count, listed.inserted_count) == (8, 5)
    assert (listed.successful_units, listed.failed_units) == (1, 0)
    assert listed.changed_count is None and listed.unchanged_count is None
    assert adapter.count_runs() == 1


def test_single_store_target_and_manual_local_day_are_preserved(repo):
    repo.run(execution="manual", TargetKind="single-store", TargetPlaceId="777")
    run = NaverReviewAdapter(repo, review_kind="visitor").get_run(RUN)
    assert run.target_place_id == "777"
    assert run.scheduled_date == date(2026, 9, 16)


def test_detail_preserves_all_attempts_without_changing_final_run_metrics(repo):
    repo.run(SourceCount=3, InsertedCount=2)
    repo.attempt(Status="FAILED", SourceCount=9, InsertedCount=0,
                 Committed=0, ErrorCategory="PAGE_LOAD_FAILED")
    repo.attempt(AttemptNo=2)
    adapter = NaverReviewAdapter(repo, review_kind="visitor")
    run = adapter.get_run(RUN)
    assert run.status == MonitoringStatus.SUCCESS
    assert (run.source_count, run.inserted_count) == (3, 2)
    assert [(item.attempt_no, item.outcome) for item in run.attempts] == [
        (1, MonitoringStatus.FAILED), (2, MonitoringStatus.SUCCESS),
    ]
    assert run.attempts[0].error_category == "PAGE_LOAD_FAILED"
    assert adapter.latest().source_count == 3
    assert adapter.count_runs_by_status(started_from=START, started_to=END) == {
        MonitoringStatus.SUCCESS: 1,
    }
    attempt = run.attempts[1]
    assert (attempt.unit_id, attempt.attempt_no, attempt.source_count) == ("123", 2, 3)
    assert "테스트점" in attempt.unit_name
    assert attempt.committed is True and attempt.error_category is None
    assert attempt.started_at.tzinfo == UTC


def test_partial_detail_preserves_final_error_and_unknown_counts(repo):
    repo.run(Status="PARTIAL_FAILED", FailedStoreCount=1, SourceCount=None, InsertedCount=None)
    repo.attempt()
    repo.attempt(PlaceId="456", Status="FAILED", SourceCount=None,
                 InsertedCount=None, Committed=0, ErrorCategory="DB_WRITE_FAILED")
    run = NaverReviewAdapter(repo, review_kind="visitor").get_run(RUN)
    assert run.status == MonitoringStatus.PARTIAL_FAILED
    assert (run.successful_units, run.failed_units) == (1, 1)
    assert run.source_count is None and run.inserted_count is None
    assert len(run.attempts) == 2
    assert run.attempts[1].outcome == MonitoringStatus.FAILED
    assert run.attempts[1].error_category == "DB_WRITE_FAILED"


def test_list_and_count_never_query_attempt_table(repo):
    repo.run()
    adapter = NaverReviewAdapter(repo, review_kind="visitor")
    assert len(adapter.list_runs()) == adapter.count_runs() == 1
    assert all("NAVER_REVIEW_COLLECTION_ATTEMPT" not in sql for sql, _ in repo.calls)


def test_filters_pagination_and_kpi_half_open_window_are_bound(repo):
    repo.run(Status="FAILED")
    repo.run(OTHER, StartedAt="2026-09-16 22:00:00", Status="FAILED")
    adapter = NaverReviewAdapter(repo, review_kind="visitor")
    filters = dict(started_from=START, started_to=END, status=MonitoringStatus.FAILED)
    assert adapter.count_runs(**filters) == 2
    assert [run.run_id for run in adapter.list_runs(**filters, offset=1, limit=1)] == [RUN]
    assert adapter.count_runs_by_status(started_from=START, started_to=END) == {
        MonitoringStatus.FAILED: 1,
    }
    for sql, parameters in repo.calls:
        assert "2026-09-15" not in sql
        assert datetime(2026, 9, 15, 22) in parameters
    assert repo.calls[1][1][-2:] == (1, 1)


@pytest.mark.parametrize("status", ["SUCCESS", "SUCCESS_EMPTY"])
def test_success_check_and_kpi_include_only_scheduled_runs(repo, status):
    repo.run(Status=status)
    repo.run(OTHER, execution="manual", CompletedAt="2026-09-16 10:00:00")
    repo.run(UUID(int=3), execution="backfill", CompletedAt="2026-09-16 11:00:00")
    adapter = NaverReviewAdapter(repo, review_kind="visitor")
    assert adapter.latest_successful_check_at() == datetime(2026, 9, 15, 22, 10, tzinfo=UTC)
    assert adapter.count_runs_by_status(started_from=START, started_to=END) == {
        MonitoringStatus(status): 1,
    }


@pytest.mark.parametrize("status", ["FAILED", "PARTIAL_FAILED", "RUNNING", "ABORTED"])
def test_failed_or_unfinished_runs_do_not_refresh_success_check(repo, status):
    repo.run(Status=status)
    assert NaverReviewAdapter(repo, review_kind="visitor").latest_successful_check_at() is None


@pytest.mark.parametrize("kind,expected", [("visitor", datetime(2026, 9, 15, 15, tzinfo=UTC)),
                                         ("blog", datetime(2026, 9, 14, 15, tzinfo=UTC))])
def test_business_dates_are_kind_specific_kst_midnight_normalized_to_utc(repo, kind, expected):
    repo.db.execute("INSERT INTO dbo.naver_review_visitor VALUES ('2026-09-16')")
    repo.db.execute("INSERT INTO dbo.naver_review_blog VALUES ('2026-09-15')")
    records = NaverReviewAdapter(repo, review_kind=kind).freshness()
    assert len(records) == 1
    assert records[0].latest_data_at == expected
    assert records[0].collector_id == f"naver-review-{kind}"
    assert records[0].dataset_id == f"{kind}-reviews"


def test_empty_source_and_readiness(repo):
    adapter = NaverReviewAdapter(repo, review_kind="visitor")
    assert adapter.latest() is None
    assert adapter.get_run(RUN) is None
    assert adapter.list_runs() == []
    assert adapter.count_runs() == 0
    assert adapter.count_runs_by_status(started_from=START, started_to=END) == {}
    assert adapter.latest_successful_check_at() is None
    assert adapter.freshness()[0].latest_data_at is None
    assert adapter.readiness() is True


@pytest.mark.parametrize("kind", ["other", "visitor; DROP TABLE anything", ""])
def test_unknown_kind_is_rejected_before_query(repo, kind):
    with pytest.raises(ValueError):
        NaverReviewAdapter(repo, review_kind=kind)
    assert repo.calls == []


@pytest.mark.parametrize("value", [datetime(2026, 9, 16),
                                   datetime(2026, 9, 16, tzinfo=timezone(timedelta(hours=9)))])
def test_non_utc_filter_is_rejected_before_query(repo, value):
    with pytest.raises(ValueError):
        NaverReviewAdapter(repo, review_kind="visitor").list_runs(started_from=value)
    assert repo.calls == []


@pytest.mark.parametrize("offset,limit", [(-1, 50), (0, 0)])
def test_invalid_pagination_is_rejected_before_query(repo, offset, limit):
    with pytest.raises(ValueError):
        NaverReviewAdapter(repo, review_kind="visitor").list_runs(offset=offset, limit=limit)
    assert repo.calls == []


def test_unapproved_error_category_cannot_leak_from_detail(repo):
    repo.run()
    repo.attempt(ErrorCategory="password=secret")
    with pytest.raises(ValueError, match="오류 분류"):
        NaverReviewAdapter(repo, review_kind="visitor").get_run(RUN)


@pytest.mark.parametrize("kind", ["visitor", "blog"])
@pytest.mark.parametrize("table", ["NAVER_REVIEW_COLLECTION_RUN", "NAVER_REVIEW_COLLECTION_ATTEMPT"])
def test_readiness_rejects_missing_audit_tables(repo, kind, table):
    repo.db.execute(f"DROP TABLE dbo.{table}")
    with pytest.raises(sqlite3.OperationalError):
        NaverReviewAdapter(repo, review_kind=kind).readiness()


@pytest.mark.parametrize("kind", ["visitor", "blog"])
@pytest.mark.parametrize("table,column", [
    ("NAVER_REVIEW_COLLECTION_RUN", "TargetStoreCount"),
    ("NAVER_REVIEW_COLLECTION_RUN", "ReviewKind"),
    ("NAVER_REVIEW_COLLECTION_RUN", "ScheduledAt"),
    ("NAVER_REVIEW_COLLECTION_ATTEMPT", "RunId"),
    ("NAVER_REVIEW_COLLECTION_ATTEMPT", "AttemptNo"),
    ("NAVER_REVIEW_COLLECTION_ATTEMPT", "ErrorCategory"),
])
def test_readiness_rejects_missing_audit_columns(repo, kind, table, column):
    repo.db.execute(f"ALTER TABLE dbo.{table} RENAME COLUMN {column} TO missing_column")
    with pytest.raises(sqlite3.OperationalError):
        NaverReviewAdapter(repo, review_kind=kind).readiness()


@pytest.mark.parametrize("kind,other", [("visitor", "blog"), ("blog", "visitor")])
@pytest.mark.parametrize("missing", ["table", "column"])
def test_readiness_checks_only_the_matching_business_table(repo, kind, other, missing):
    if missing == "table":
        repo.db.execute(f"DROP TABLE dbo.naver_review_{kind}")
    else:
        repo.db.execute(f"ALTER TABLE dbo.naver_review_{kind} RENAME COLUMN date TO missing_date")
    assert NaverReviewAdapter(repo, review_kind=other).readiness() is True
    with pytest.raises(sqlite3.OperationalError):
        NaverReviewAdapter(repo, review_kind=kind).readiness()


def test_readiness_permission_error_is_sanitized_by_service(repo):
    from monitoring_api.services.monitoring import MonitoringService

    def deny_attempt_read(action, table, *args):
        if action == sqlite3.SQLITE_READ and table == "NAVER_REVIEW_COLLECTION_ATTEMPT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    repo.db.set_authorizer(deny_attempt_read)
    result = MonitoringService([NaverReviewAdapter(repo, review_kind="visitor")]).readiness()
    assert result.items[0].ready is False
    assert result.errors[0].code == "SOURCE_UNAVAILABLE"
    assert "NAVER_REVIEW_COLLECTION_ATTEMPT" not in result.model_dump_json()


@pytest.mark.parametrize("target_count", [None, 0, 7])
def test_target_count_is_preserved_in_all_run_views(repo, target_count):
    repo.run(TargetStoreCount=target_count)
    adapter = NaverReviewAdapter(repo, review_kind="visitor")
    for run in [adapter.latest(), adapter.list_runs()[0], adapter.get_run(RUN)]:
        assert run.model_dump(mode="json")["target_store_count"] == target_count


def test_http_detail_exposes_target_count_and_full_retry_history(repo):
    from fastapi.testclient import TestClient
    from auth_helpers import create_admin_app
    from monitoring_api.config import Settings
    from monitoring_api.services.monitoring import MonitoringService

    repo.run(TargetStoreCount=7)
    repo.attempt(Status="FAILED", Committed=0, ErrorCategory="PAGE_LOAD_FAILED")
    repo.attempt(AttemptNo=2)
    service = MonitoringService([NaverReviewAdapter(repo, review_kind="visitor")])
    with TestClient(create_admin_app(Settings(_env_file=None), monitoring_service=service)) as client:
        response = client.get(f"/api/v1/monitoring/runs/naver-review-visitor/{RUN}")
    assert response.status_code == 200
    run = response.json()["items"][0]
    assert run["target_store_count"] == 7
    assert "TargetStoreCount" not in run
    assert [item["attempt_no"] for item in run["attempts"]] == [1, 2]
