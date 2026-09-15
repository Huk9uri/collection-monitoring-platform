"""정제된 영업시간 감사 레코드를 SELECT 전용으로 조회한다."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from monitoring_api.adapters.base import (
    CollectorAttempt,
    CollectorRun,
    FreshnessRecord,
    as_utc,
    require_utc_datetime,
    to_sql_datetime,
)
from monitoring_api.models import MonitoringStatus

NAMESPACE = UUID("a354f224-e8ef-4ae1-9384-d78238004f78")
BRANDS = {"001": ("hanchon", "한촌설렁탕"), "002": ("yuksoodang", "육수당")}
ERRORS = {
    "PREFLIGHT_FAILED",
    "DRY_RUN_FAILED",
    "APPLY_FAILED",
    "ARTIFACT_INVALID",
    "PREREQUISITE_FAILED",
    "COLLECTION_FAILED",
    "INVALID_PLACE",
    "HOURS_NOT_PROVIDED",
    "REVIEW_REQUIRED",
    "MONITORING_INCOMPLETE",
}
RAW_STATUSES = {"SUCCESS", "PARTIAL_FAILURE", "FAILED", "RUNNING"}
COLUMNS = "RunId AS run_id, ParentRunId AS parent_run_id, SourceInstance AS source_instance, OriginalRunId AS original_run_id, BrandCode AS brand_code, ExecutionKind AS execution_kind, StartedAt AS started_at, CompletedAt AS completed_at, Status AS status, Payload AS payload"
TABLE = "dbo.NAVER_STORE_HOURS_MONITORING_RUN"
FILTER = "(? IS NULL OR StartedAt >= ?) AND (? IS NULL OR StartedAt <= ?) AND (? IS NULL OR Status = ?) AND (? IS NULL OR BrandCode = ?)"
LIST_SQL = f"SELECT {COLUMNS} FROM {TABLE} WHERE {FILTER} ORDER BY StartedAt DESC, CONVERT(char(36), RunId) DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
COUNT_SQL = f"SELECT COUNT_BIG(*) AS total FROM {TABLE} WHERE {FILTER}"
STATUS_SQL = f"SELECT Status AS status, COUNT_BIG(*) AS total FROM {TABLE} WHERE ExecutionKind = 'scheduled' AND StartedAt >= ? AND StartedAt < ? GROUP BY Status"
RUN_SQL = f"SELECT {COLUMNS} FROM {TABLE} WHERE RunId = ?"
LATEST_SQL = f"WITH ranked AS (SELECT {COLUMNS}, ROW_NUMBER() OVER (PARTITION BY BrandCode ORDER BY StartedAt DESC, RunId DESC) AS rn FROM {TABLE} WHERE ExecutionKind = 'scheduled') SELECT * FROM ranked WHERE rn = 1"
SUCCESS_SQL = f"WITH ranked AS (SELECT {COLUMNS}, ROW_NUMBER() OVER (PARTITION BY BrandCode ORDER BY CompletedAt DESC, RunId DESC) AS rn FROM {TABLE} WHERE ExecutionKind = 'scheduled' AND CompletedAt IS NOT NULL AND JSON_VALUE(Payload, '$.successful_check_at') IS NOT NULL) SELECT * FROM ranked WHERE rn = 1"
OCCURRENCE_SQL = f"SELECT {COLUMNS} FROM {TABLE} WHERE ExecutionKind = 'scheduled' AND StartedAt >= ? AND StartedAt < ? ORDER BY StartedAt DESC, RunId DESC"


@dataclass(frozen=True)
class StoreHoursPolicy:
    schedule_timezone: str
    weekly_scheduled_day: int
    weekly_scheduled_time: time
    start_grace: timedelta
    max_duration: timedelta
    attribution_window: timedelta

    def __post_init__(self):
        ZoneInfo(self.schedule_timezone)
        if (
            not 0 <= self.weekly_scheduled_day <= 6
            or self.weekly_scheduled_time.tzinfo is not None
        ):
            raise ValueError("주간 예정 요일과 현지 시각이 유효하지 않습니다.")
        if not timedelta(0) < self.start_grace <= self.attribution_window < timedelta(
            days=7
        ) or self.max_duration <= timedelta(0):
            raise ValueError("주간 정책 기간이 유효하지 않습니다.")

    def occurrence(self, now: datetime) -> datetime:
        require_utc_datetime(now)
        zone = ZoneInfo(self.schedule_timezone)
        local = now.astimezone(zone)
        day = local.date() - timedelta(
            days=(local.weekday() - self.weekly_scheduled_day) % 7
        )
        due = datetime.combine(day, self.weekly_scheduled_time, tzinfo=zone).astimezone(
            UTC
        )
        if now < due + self.start_grace:
            due = datetime.combine(
                day - timedelta(days=7), self.weekly_scheduled_time, tzinfo=zone
            ).astimezone(UTC)
        return due


def _validate_counts(data):
    for key, value in data.items():
        if key.endswith("_count") or key in {
            "successful_units",
            "failed_units",
            "attempt_no",
        }:
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("건수가 유효하지 않습니다.")
    if data.get("committed") is not None and type(data["committed"]) is not bool:
        raise ValueError("반영 여부가 유효하지 않습니다.")
    if data.get("error_category") is not None and data["error_category"] not in ERRORS:
        raise ValueError("오류 분류가 유효하지 않습니다.")
    if data.get("raw_status") not in RAW_STATUSES:
        raise ValueError("원본 상태가 유효하지 않습니다.")


def parse_run(row) -> CollectorRun:
    """알 수 없는 키와 자유 형식 문자열을 거부하고 SQL 식별자를 대조한다."""
    data = json.loads(row["payload"])
    if not isinstance(data, dict) or set(data) - set(CollectorRun.model_fields):
        raise ValueError("정제된 실행 계약이 아닙니다.")
    _validate_counts(data)
    scope = BRANDS.get(row["brand_code"])
    if (
        scope is None
        or (data.get("scope_id"), data.get("scope_name")) != scope
        or data.get("collector_id") != "naver-store-hours"
    ):
        raise ValueError("수집기 또는 브랜드가 일치하지 않습니다.")
    for attempt in data.get("attempts", []):
        if not isinstance(attempt, dict) or set(attempt) - set(
            CollectorAttempt.model_fields
        ):
            raise ValueError("정제된 시도 계약이 아닙니다.")
        _validate_counts(attempt)
        stage = attempt.get("stage")
        if stage not in {"dry-run", "apply"} or attempt.get("unit_id") not in {
            stage,
            f"{stage}:{attempt.get('child_run_id')}",
        }:
            raise ValueError("시도 단계가 유효하지 않습니다.")
        if attempt.get("unit_name") not in {
            "dry-run",
            "apply",
            "사전 수집",
            "안전 반영",
            "드라이런",
            "Apply",
            "수집 사전 검증",
            "안전 대상 DB 반영",
        }:
            raise ValueError("시도 표시명이 유효하지 않습니다.")
        if attempt.get("attempt_no", 0) < 1:
            raise ValueError("시도 번호가 유효하지 않습니다.")
        if any(
            not isinstance(code, str) or not re.fullmatch(r"[0-9A-Za-z_-]{1,30}", code)
            for code in (attempt.get("store_codes") or [])
        ):
            raise ValueError("매장 코드가 유효하지 않습니다.")
    run = CollectorRun.model_validate(data)
    if len({(attempt.unit_id, attempt.attempt_no) for attempt in run.attempts}) != len(
        run.attempts
    ):
        raise ValueError("중복 시도입니다.")
    if run.execution_kind == "preflight-only" and (
        run.attempts
        or run.successful_units
        or run.failed_units
        or run.committed is not None
        or any(
            getattr(run, key) is not None
            for key in (
                "source_count",
                "inserted_count",
                "changed_count",
                "unchanged_count",
                "review_count",
                "failure_count",
                "applied_count",
                "coverage_count",
                "successful_check_at",
            )
        )
    ):
        raise ValueError("사전 점검은 수집 지표를 포함할 수 없습니다.")
    parent = uuid5(
        NAMESPACE,
        json.dumps(
            [row["source_instance"], row["original_run_id"]],
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    )
    if (
        run.parent_run_id != parent
        or UUID(str(row["parent_run_id"])) != parent
        or run.run_id != uuid5(parent, row["brand_code"])
        or UUID(str(row["run_id"])) != run.run_id
    ):
        raise ValueError("실행 식별자가 일치하지 않습니다.")
    if (
        run.execution_kind != row["execution_kind"]
        or run.status.value != row["status"]
        or run.started_at != as_utc(row["started_at"])
        or run.completed_at != as_utc(row["completed_at"])
    ):
        raise ValueError("실행 상태 또는 시각이 일치하지 않습니다.")
    if run.completed_at is not None and run.completed_at < run.started_at:
        raise ValueError("완료 시각이 유효하지 않습니다.")
    if (run.status == MonitoringStatus.RUNNING) != (run.completed_at is None):
        raise ValueError("실행 완료 상태가 유효하지 않습니다.")
    if run.successful_check_at is not None:
        if (
            run.status not in {MonitoringStatus.SUCCESS, MonitoringStatus.SUCCESS_EMPTY}
            or run.source_count is None
            or run.coverage_count != run.source_count
            or run.applied_count is None
        ):
            raise ValueError("전체 성공 확인 근거가 없습니다.")
        require_utc_datetime(run.successful_check_at)
        if (
            run.execution_kind != "scheduled"
            or run.completed_at is None
            or not run.started_at <= run.successful_check_at <= run.completed_at
        ):
            raise ValueError("성공 확인 시각이 유효하지 않습니다.")
    for attempt in run.attempts:
        if attempt.started_at < run.started_at or (
            attempt.completed_at is not None
            and (
                attempt.completed_at < attempt.started_at
                or (
                    run.completed_at is not None
                    and attempt.completed_at > run.completed_at
                )
            )
        ):
            raise ValueError("시도 시각이 유효하지 않습니다.")
    return run


class NaverStoreHoursAdapter:
    collector_id = "naver-store-hours"
    display_name = "네이버 매장 영업시간"
    supports_scope_filter = True

    def with_monitoring_policy(self, policy):
        from copy import copy
        from types import SimpleNamespace
        from monitoring_api.services.policy import previous_occurrence
        result = copy(self)
        result._policy = SimpleNamespace(
            schedule_timezone=policy.timezone_name,
            max_duration=timedelta(minutes=policy.max_duration_minutes) if policy.max_duration_minutes else timedelta.max,
            attribution_window=timedelta(minutes=policy.schedule_attribution_window_minutes),
            occurrence=lambda now: previous_occurrence(policy, now - timedelta(minutes=policy.start_grace_minutes)),
        ) if policy.monitoring_enabled else None
        return result

    def __init__(self, repository, *, policy=None, clock=None):
        self._repository = repository
        self._policy = policy
        self._clock = clock or (lambda: datetime.now(UTC))

    def _parameters(self, started_from, started_to, status, scope_id):
        brand = None
        if scope_id is not None:
            brand = next(
                (code for code, scope in BRANDS.items() if scope[0] == scope_id),
                "__unknown__",
            )
        start, end = to_sql_datetime(started_from), to_sql_datetime(started_to)
        value = None if status is None else status.value
        return (start, start, end, end, value, value, brand, brand)

    def list_runs(
        self,
        *,
        started_from=None,
        started_to=None,
        status=None,
        scope_id=None,
        offset=0,
        limit=50,
    ):
        rows = self._repository.fetch_all(
            LIST_SQL,
            self._parameters(started_from, started_to, status, scope_id)
            + (offset, limit),
        )
        return [parse_run(row) for row in rows]

    def count_runs(
        self, *, started_from=None, started_to=None, status=None, scope_id=None
    ):
        rows = self._repository.fetch_all(
            COUNT_SQL, self._parameters(started_from, started_to, status, scope_id)
        )
        return int(rows[0]["total"]) if rows else 0

    def count_runs_by_status(self, *, started_from, started_to):
        return {
            MonitoringStatus(row["status"]): int(row["total"])
            for row in self._repository.fetch_all(
                STATUS_SQL, (to_sql_datetime(started_from), to_sql_datetime(started_to))
            )
        }

    def latest(self):
        if self._policy is None:
            rows = self._repository.fetch_all(LATEST_SQL)
            runs = [parse_run(row) for row in rows]
        else:
            now = self._clock()
            due = self._policy.occurrence(now)
            rows = self._repository.fetch_all(
                OCCURRENCE_SQL,
                (
                    to_sql_datetime(due),
                    to_sql_datetime(due + self._policy.attribution_window),
                ),
            )
            by_scope = {}
            for row in rows:
                run = parse_run(row)
                by_scope.setdefault(run.scope_id, run)
            runs = list(by_scope.values())
            for scope_id, name in BRANDS.values():
                if scope_id not in by_scope:
                    runs.append(
                        CollectorRun(
                            collector_id=self.collector_id,
                            run_id=uuid5(
                                NAMESPACE, f"not-run:{due.isoformat()}:{scope_id}"
                            ),
                            scheduled_date=due.astimezone(
                                ZoneInfo(self._policy.schedule_timezone)
                            ).date(),
                            started_at=due,
                            completed_at=None,
                            status=MonitoringStatus.NOT_RUN,
                            successful_units=0,
                            failed_units=0,
                            source_count=None,
                            inserted_count=None,
                            changed_count=None,
                            unchanged_count=None,
                            scope_id=scope_id,
                            scope_name=name,
                            execution_kind="scheduled",
                        )
                    )
            runs = [
                (
                    run.model_copy(update={"status": MonitoringStatus.ABORTED})
                    if run.status == MonitoringStatus.RUNNING
                    and now - run.started_at > self._policy.max_duration
                    else run
                )
                for run in runs
            ]
        severity = {
            MonitoringStatus.FAILED: 8,
            MonitoringStatus.ABORTED: 7,
            MonitoringStatus.PARTIAL_FAILED: 6,
            MonitoringStatus.WARNING: 5,
            MonitoringStatus.RUNNING: 4,
            MonitoringStatus.NOT_RUN: 3,
            MonitoringStatus.SUCCESS_EMPTY: 2,
            MonitoringStatus.SUCCESS: 1,
        }
        return max(
            runs,
            key=lambda run: (severity[run.status], run.started_at, str(run.run_id)),
            default=None,
        )

    def get_run(self, run_id):
        rows = self._repository.fetch_all(RUN_SQL, (str(run_id),))
        if rows:
            return parse_run(rows[0])
        if self._policy is not None:
            latest = self.latest()
            if latest is not None and latest.run_id == run_id:
                return latest
        return None

    def latest_successful_check_at(self):
        values = [
            parse_run(row).successful_check_at
            for row in self._repository.fetch_all(SUCCESS_SQL)
        ]
        return max((value for value in values if value is not None), default=None)

    def freshness(self):
        latest = {
            run.scope_id: run
            for run in (
                parse_run(row) for row in self._repository.fetch_all(LATEST_SQL)
            )
        }
        successful = {
            run.scope_id: run
            for run in (
                parse_run(row) for row in self._repository.fetch_all(SUCCESS_SQL)
            )
        }
        return [
            FreshnessRecord(
                collector_id=self.collector_id,
                dataset_id=scope_id,
                scope_id=scope_id,
                scope_name=name,
                latest_data_at=None,
                last_successful_check_at=(
                    successful[scope_id].successful_check_at
                    if scope_id in successful
                    else None
                ),
                coverage_count=(
                    latest[scope_id].coverage_count if scope_id in latest else None
                ),
                source_count=(
                    latest[scope_id].source_count if scope_id in latest else None
                ),
            )
            for scope_id, name in BRANDS.values()
        ]

    def readiness(self):
        return self._repository.ping()
