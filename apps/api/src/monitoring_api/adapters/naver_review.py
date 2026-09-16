"""네이버 방문자·블로그 리뷰 감사와 업무 날짜를 읽기 전용으로 정규화한다."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Literal, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from monitoring_api.adapters.base import (
    CollectorAttempt,
    CollectorRun,
    FreshnessRecord,
    as_utc,
    to_sql_datetime,
)
from monitoring_api.models import MonitoringStatus


class QueryRepository(Protocol):
    def fetch_all(
        self, sql: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]: ...

    def ping(self) -> bool: ...


_KST = ZoneInfo("Asia/Seoul")
_ERRORS = {
    "CAPTCHA_DETECTED", "PAGE_LOAD_FAILED", "PARSE_FAILED", "DB_WRITE_FAILED",
    "BRAND_MAPPING_FAILED", "UNEXPECTED_ERROR",
}
_STATUSES = {"RUNNING", "SUCCESS", "SUCCESS_EMPTY", "PARTIAL_FAILED", "FAILED", "ABORTED"}
_COLUMNS = """
    RunId AS run_id, ExecutionKind AS execution_kind, TargetKind AS target_kind,
    ScheduledAt AS scheduled_at, StartedAt AS started_at, CompletedAt AS completed_at,
    Status AS raw_status, SuccessfulStoreCount AS successful_units,
    FailedStoreCount AS failed_units, SourceCount AS source_count,
    InsertedCount AS inserted_count, TargetDateFrom AS target_date_from,
    TargetDateTo AS target_date_to, TargetPlaceId AS target_place_id
"""
_FILTER = """ReviewKind = ?
    AND (? IS NULL OR StartedAt >= ?)
    AND (? IS NULL OR StartedAt <= ?)
    AND (? IS NULL OR Status = ?)"""

LATEST_SQL = f"""SELECT TOP (1) {_COLUMNS}
FROM dbo.NAVER_REVIEW_COLLECTION_RUN
WHERE ReviewKind = ? AND ExecutionKind = 'scheduled'
ORDER BY ScheduledAt DESC, StartedAt DESC, CONVERT(char(36), RunId) DESC"""

LIST_SQL = f"""SELECT {_COLUMNS} FROM dbo.NAVER_REVIEW_COLLECTION_RUN
WHERE {_FILTER}
ORDER BY StartedAt DESC, CONVERT(char(36), RunId) DESC
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"""

COUNT_SQL = f"""SELECT COUNT_BIG(*) AS total FROM dbo.NAVER_REVIEW_COLLECTION_RUN
WHERE {_FILTER}"""

STATUS_SQL = """SELECT Status AS status, COUNT_BIG(*) AS total
FROM dbo.NAVER_REVIEW_COLLECTION_RUN
WHERE ReviewKind = ? AND ExecutionKind = 'scheduled'
    AND StartedAt >= ? AND StartedAt < ?
GROUP BY Status"""

SUCCESS_SQL = """SELECT TOP (1) CompletedAt AS last_successful_check_at
FROM dbo.NAVER_REVIEW_COLLECTION_RUN
WHERE ReviewKind = ? AND ExecutionKind = 'scheduled'
    AND Status IN ('SUCCESS', 'SUCCESS_EMPTY') AND CompletedAt IS NOT NULL
ORDER BY CompletedAt DESC, CONVERT(char(36), RunId) DESC"""

RUN_SQL = f"""SELECT {_COLUMNS} FROM dbo.NAVER_REVIEW_COLLECTION_RUN
WHERE ReviewKind = ? AND RunId = ?"""

ATTEMPTS_SQL = """SELECT
    attempt.PlaceId AS unit_id,
    CONCAT(attempt.BrandName, ' / ', attempt.StoreName) AS unit_name,
    attempt.AttemptNo AS attempt_no, attempt.StartedAt AS started_at,
    attempt.CompletedAt AS completed_at, attempt.Status AS raw_status,
    attempt.SourceCount AS source_count, attempt.InsertedCount AS inserted_count,
    attempt.Committed AS committed, attempt.ErrorCategory AS error_category
FROM dbo.NAVER_REVIEW_COLLECTION_ATTEMPT AS attempt
INNER JOIN dbo.NAVER_REVIEW_COLLECTION_RUN AS run ON run.RunId = attempt.RunId
WHERE run.ReviewKind = ? AND run.RunId = ?
    AND attempt.AttemptNo = (
        SELECT MAX(final.AttemptNo) FROM dbo.NAVER_REVIEW_COLLECTION_ATTEMPT AS final
        WHERE final.RunId = attempt.RunId AND final.PlaceId = attempt.PlaceId
    )
ORDER BY attempt.PlaceId"""

# 외부 입력으로 테이블명을 조립하지 않는다. 업무 테이블은 날짜 정밀도다.
FRESHNESS_SQL = {
    "visitor": "SELECT MAX(CONVERT(date, [date])) AS latest_date FROM dbo.naver_review_visitor",
    "blog": "SELECT MAX(CONVERT(date, [date])) AS latest_date FROM dbo.naver_review_blog",
}
DATASET_IDS = {
    "visitor": "visitor-reviews",
    "blog": "blog-reviews",
}


def _status(value: object) -> MonitoringStatus:
    if value not in _STATUSES:
        raise ValueError("리뷰 실행 상태가 유효하지 않습니다.")
    return MonitoringStatus(value)


def _attempt(row: dict[str, object]) -> CollectorAttempt:
    error_category = row.get("error_category")
    if error_category is not None and error_category not in _ERRORS:
        raise ValueError("리뷰 오류 분류가 유효하지 않습니다.")
    status = _status(row["raw_status"])
    return CollectorAttempt(
        unit_id=row["unit_id"], unit_name=row["unit_name"],
        attempt_no=row["attempt_no"],
        started_at=as_utc(row["started_at"]),
        completed_at=as_utc(row.get("completed_at")),
        raw_status=status.value, outcome=status,
        source_count=row.get("source_count"), inserted_count=row.get("inserted_count"),
        changed_count=None, unchanged_count=None,
        committed=row.get("committed"), error_category=error_category,
    )


class NaverReviewAdapter:
    def __init__(
        self, repository: QueryRepository, *, review_kind: Literal["visitor", "blog"]
    ) -> None:
        if review_kind not in FRESHNESS_SQL:
            raise ValueError("지원하지 않는 리뷰 종류입니다.")
        self._repository = repository
        self.review_kind = review_kind
        self.collector_id = f"naver-review-{review_kind}"
        self.display_name = "네이버 방문자 리뷰" if review_kind == "visitor" else "네이버 블로그 리뷰"

    def _run(
        self, row: dict[str, object], attempts: list[CollectorAttempt] | None = None
    ) -> CollectorRun:
        started = as_utc(row["started_at"])
        completed = as_utc(row.get("completed_at"))
        scheduled = as_utc(row.get("scheduled_at")) or started
        status = _status(row["raw_status"])
        # RUN은 수집기가 PlaceId별 최종 AttemptNo로 확정한 집계다.
        # 재시도 성공은 SUCCESS이며 다른 수집기의 WARNING 승격 규칙을 적용하지 않는다.
        return CollectorRun(
            collector_id=self.collector_id, run_id=row["run_id"],
            scheduled_date=scheduled.astimezone(_KST).date(),
            started_at=started, completed_at=completed, status=status,
            raw_status=status.value, execution_kind=row["execution_kind"],
            target_kind=row["target_kind"], target_date_from=row.get("target_date_from"),
            target_date_to=row.get("target_date_to"), target_place_id=row.get("target_place_id"),
            successful_units=row["successful_units"], failed_units=row["failed_units"],
            source_count=row.get("source_count"), inserted_count=row.get("inserted_count"),
            changed_count=None, unchanged_count=None,
            successful_check_at=(
                completed if row["execution_kind"] == "scheduled"
                and status in {MonitoringStatus.SUCCESS, MonitoringStatus.SUCCESS_EMPTY}
                else None
            ),
            attempts=attempts or [],
        )

    def _filters(
        self,
        started_from: datetime | None,
        started_to: datetime | None,
        status: MonitoringStatus | None,
    ) -> tuple[object, ...]:
        start = to_sql_datetime(started_from)
        end = to_sql_datetime(started_to)
        status_value = None if status is None else status.value
        return self.review_kind, start, start, end, end, status_value, status_value

    def latest(self) -> CollectorRun | None:
        rows = self._repository.fetch_all(LATEST_SQL, (self.review_kind,))
        return self._run(rows[0]) if rows else None

    def list_runs(
        self, *, started_from: datetime | None = None, started_to: datetime | None = None,
        status: MonitoringStatus | None = None, offset: int = 0, limit: int = 50,
    ) -> list[CollectorRun]:
        if offset < 0 or limit < 1:
            raise ValueError("페이지 범위가 유효하지 않습니다.")
        rows = self._repository.fetch_all(
            LIST_SQL, self._filters(started_from, started_to, status) + (offset, limit),
        )
        return [self._run(row) for row in rows]

    def count_runs(
        self, *, started_from: datetime | None = None, started_to: datetime | None = None,
        status: MonitoringStatus | None = None,
    ) -> int:
        rows = self._repository.fetch_all(COUNT_SQL, self._filters(started_from, started_to, status))
        return int(rows[0]["total"]) if rows else 0

    def count_runs_by_status(
        self, *, started_from: datetime, started_to: datetime,
    ) -> dict[MonitoringStatus, int]:
        rows = self._repository.fetch_all(
            STATUS_SQL, (self.review_kind, to_sql_datetime(started_from), to_sql_datetime(started_to)),
        )
        return {_status(row["status"]): int(row["total"]) for row in rows}

    def latest_successful_check_at(self) -> datetime | None:
        rows = self._repository.fetch_all(SUCCESS_SQL, (self.review_kind,))
        return as_utc(rows[0]["last_successful_check_at"]) if rows else None

    def get_run(self, run_id: UUID) -> CollectorRun | None:
        parameters = (self.review_kind, str(run_id))
        rows = self._repository.fetch_all(RUN_SQL, parameters)
        if not rows:
            return None
        attempts = self._repository.fetch_all(ATTEMPTS_SQL, parameters)
        return self._run(rows[0], [_attempt(row) for row in attempts])

    def freshness(self) -> list[FreshnessRecord]:
        rows = self._repository.fetch_all(FRESHNESS_SQL[self.review_kind])
        latest = rows[0].get("latest_date") if rows else None
        if isinstance(latest, datetime):
            latest = latest.date()
        elif latest is not None and not isinstance(latest, date):
            latest = date.fromisoformat(str(latest))
        return [FreshnessRecord(
            collector_id=self.collector_id, dataset_id=DATASET_IDS[self.review_kind],
            latest_data_at=(
                datetime.combine(latest, time.min, tzinfo=_KST).astimezone(UTC)
                if latest is not None else None
            ),
        )]

    def readiness(self) -> bool:
        return self._repository.ping()
