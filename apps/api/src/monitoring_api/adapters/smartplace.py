"""naverDB SmartPlace 실행 감사 테이블의 읽기 전용 어댑터다."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Protocol
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from monitoring_api.adapters.base import (
    CollectorAttempt,
    CollectorRun,
    FreshnessRecord,
    as_utc,
    attempt_from_row,
    map_raw_status,
    run_from_row,
    to_sql_datetime,
)
from monitoring_api.models import MonitoringStatus


class QueryRepository(Protocol):
    def fetch_all(
        self, sql: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]: ...

    def ping(self) -> bool: ...


@dataclass(frozen=True)
class ExpectedScope:
    scope_id: str
    scope_name: str

    def __post_init__(self) -> None:
        if not self.scope_id.strip() or not self.scope_name.strip():
            raise ValueError("SmartPlace 예상 scope 값은 비어 있을 수 없습니다.")


@dataclass(frozen=True)
class SmartPlacePolicy:
    schedule_timezone: str
    daily_scheduled_time: time
    start_grace: timedelta
    max_duration: timedelta
    expected_scopes: tuple[ExpectedScope, ...]
    attribution_window: timedelta = timedelta(minutes=60)

    def __post_init__(self) -> None:
        ZoneInfo(self.schedule_timezone)
        if self.daily_scheduled_time.tzinfo is not None:
            raise ValueError("SmartPlace 예정 시각은 timezone 없는 현지 시각이어야 합니다.")
        if self.start_grace <= timedelta(0):
            raise ValueError("SmartPlace 시작 유예시간은 양수여야 합니다.")
        if self.max_duration <= timedelta(0):
            raise ValueError("SmartPlace 최대 실행시간은 양수여야 합니다.")
        if self.attribution_window <= timedelta(0):
            raise ValueError("SmartPlace 예약 귀속 창은 양수여야 합니다.")
        if self.attribution_window < self.start_grace:
            raise ValueError("SmartPlace 예약 귀속 창은 시작 유예시간 이상이어야 합니다.")
        if self.attribution_window >= timedelta(days=1):
            raise ValueError("SmartPlace 예약 귀속 창은 일일 주기보다 짧아야 합니다.")
        if not self.expected_scopes:
            raise ValueError("SmartPlace 예상 scope가 하나 이상 필요합니다.")
        scope_ids = [scope.scope_id for scope in self.expected_scopes]
        if len(scope_ids) != len(set(scope_ids)):
            raise ValueError("SmartPlace 예상 scope ID는 중복될 수 없습니다.")


@dataclass(frozen=True)
class _ScheduledOccurrence:
    scheduled_at: datetime
    local_scheduled_at: datetime
    range_start: datetime
    range_end: datetime


_SMARTPLACE_RAW_STATUS_SQL = """CASE UPPER(LTRIM(RTRIM(runs.RunStatus)))
    WHEN 'SUCCESS' THEN 'SUCCESS'
    WHEN 'SUCCESS_WITH_DATA' THEN 'SUCCESS'
    WHEN 'SUCCESS_EMPTY' THEN 'SUCCESS_EMPTY'
    WHEN 'WARNING' THEN 'WARNING'
    WHEN 'PARTIAL' THEN 'PARTIAL_FAILED'
    WHEN 'PARTIAL_FAILED' THEN 'PARTIAL_FAILED'
    WHEN 'FAILED' THEN 'FAILED'
    WHEN 'RUNNING' THEN 'RUNNING'
    WHEN 'ABORTED' THEN 'ABORTED'
    ELSE 'FAILED' END"""

_SMARTPLACE_CANONICAL_STATUS_SQL = _SMARTPLACE_RAW_STATUS_SQL

_DYNAMIC_STATUS_SQL = f"""CASE
    WHEN {_SMARTPLACE_RAW_STATUS_SQL} = 'RUNNING'
      AND runs.StartedAt < COALESCE(?, runs.StartedAt)
        THEN 'ABORTED'
    ELSE {_SMARTPLACE_CANONICAL_STATUS_SQL} END"""

_RUN_COLUMNS = """
    runs.RunId AS run_id,
    runs.ScheduledAt AS scheduled_at,
    runs.StartedAt AS started_at,
    runs.FinishedAt AS completed_at,
    runs.RunStatus AS raw_status,
    runs.SuccessfulUnits AS successful_units,
    runs.FailedUnits AS failed_units,
    runs.BrandCode AS scope_id,
    runs.BrandName AS scope_name
"""

SMARTPLACE_LIST_SQL = f"""WITH normalized_runs AS (
    SELECT
{_RUN_COLUMNS},
        {_DYNAMIC_STATUS_SQL} AS canonical_status
    FROM dbo.SMARTPLACE_COLLECTION_RUN AS runs
)
SELECT
    run_id, scheduled_at, started_at, completed_at, raw_status,
    successful_units, failed_units, scope_id, scope_name, canonical_status
FROM normalized_runs
WHERE (? IS NULL OR started_at >= ?)
  AND (? IS NULL OR started_at <= ?)
  AND (? IS NULL OR canonical_status = ?)
ORDER BY started_at DESC, CONVERT(char(36), run_id) DESC
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"""

SMARTPLACE_OCCURRENCE_RUNS_SQL = f"""WITH normalized_runs AS (
    SELECT
{_RUN_COLUMNS},
        {_DYNAMIC_STATUS_SQL} AS canonical_status
    FROM dbo.SMARTPLACE_COLLECTION_RUN AS runs
)
SELECT
    run_id, scheduled_at, started_at, completed_at, raw_status,
    successful_units, failed_units, scope_id, scope_name, canonical_status
FROM normalized_runs
WHERE scheduled_at >= ? AND scheduled_at < ?
ORDER BY scheduled_at DESC, started_at DESC, CONVERT(char(36), run_id) DESC"""

SMARTPLACE_COUNT_SQL = f"""WITH normalized_runs AS (
    SELECT runs.StartedAt AS started_at,
           {_DYNAMIC_STATUS_SQL} AS canonical_status
    FROM dbo.SMARTPLACE_COLLECTION_RUN AS runs
)
SELECT COUNT_BIG(*) AS total
FROM normalized_runs
WHERE (? IS NULL OR started_at >= ?)
  AND (? IS NULL OR started_at <= ?)
  AND (? IS NULL OR canonical_status = ?)"""

SMARTPLACE_STATUS_COUNTS_SQL = f"""WITH normalized_runs AS (
    SELECT runs.StartedAt AS started_at,
           {_DYNAMIC_STATUS_SQL} AS canonical_status
    FROM dbo.SMARTPLACE_COLLECTION_RUN AS runs
)
SELECT canonical_status AS status, COUNT_BIG(*) AS total
FROM normalized_runs
WHERE started_at >= ? AND started_at < ?
GROUP BY canonical_status"""

SMARTPLACE_LATEST_SUCCESS_SQL = f"""SELECT TOP (1)
    runs.FinishedAt AS last_successful_check_at
FROM dbo.SMARTPLACE_COLLECTION_RUN AS runs
WHERE runs.FinishedAt IS NOT NULL
  AND {_SMARTPLACE_CANONICAL_STATUS_SQL}
      IN ('SUCCESS', 'SUCCESS_EMPTY', 'WARNING')
ORDER BY runs.FinishedAt DESC, CONVERT(char(36), runs.RunId) DESC"""

SMARTPLACE_RUN_SQL = f"""SELECT
{_RUN_COLUMNS}
FROM dbo.SMARTPLACE_COLLECTION_RUN AS runs
WHERE runs.RunId = ?"""

SMARTPLACE_ATTEMPTS_SQL = """SELECT
    UnitCode AS unit_id,
    UnitName AS unit_name,
    AttemptNo AS attempt_no,
    StartedAt AS started_at,
    FinishedAt AS completed_at,
    AttemptStatus AS raw_status,
    SourceCount AS source_count,
    InsertedCount AS inserted_count,
    ChangedCount AS changed_count,
    UnchangedCount AS unchanged_count,
    DbCommitted AS committed,
    ErrorCategory AS error_category
FROM dbo.SMARTPLACE_COLLECTION_ATTEMPT
WHERE RunId = ?
ORDER BY CASE UnitCode
             WHEN 'login' THEN 1 WHEN 'normal' THEN 2
             WHEN 'pos_linked' THEN 3 ELSE 4 END,
         UnitCode, AttemptNo"""

SMARTPLACE_ATTEMPTS_FOR_RUNS_SQL = """SELECT
    RunId AS run_id,
    UnitCode AS unit_id,
    UnitName AS unit_name,
    AttemptNo AS attempt_no,
    StartedAt AS started_at,
    FinishedAt AS completed_at,
    AttemptStatus AS raw_status,
    SourceCount AS source_count,
    InsertedCount AS inserted_count,
    ChangedCount AS changed_count,
    UnchangedCount AS unchanged_count,
    DbCommitted AS committed,
    ErrorCategory AS error_category
FROM dbo.SMARTPLACE_COLLECTION_ATTEMPT
WHERE RunId IN (
    SELECT TRY_CONVERT(uniqueidentifier, [value]) FROM OPENJSON(?)
)
ORDER BY RunId,
         CASE UnitCode
             WHEN 'login' THEN 1 WHEN 'normal' THEN 2
             WHEN 'pos_linked' THEN 3 ELSE 4 END,
         UnitCode, AttemptNo"""

SMARTPLACE_PRESENT_SCOPES_SQL = """SELECT BrandCode AS scope_id
FROM dbo.SMARTPLACE_COLLECTION_RUN
WHERE ScheduledAt >= ? AND ScheduledAt < ?"""


_SYNTHETIC_NAMESPACE = UUID("5d2b2540-bcf7-47be-8e58-5d739f8c8bc3")
_STATUS_SEVERITY = {
    MonitoringStatus.FAILED: 8,
    MonitoringStatus.ABORTED: 7,
    MonitoringStatus.PARTIAL_FAILED: 6,
    MonitoringStatus.WARNING: 5,
    MonitoringStatus.RUNNING: 4,
    MonitoringStatus.NOT_RUN: 3,
    MonitoringStatus.SUCCESS_EMPTY: 2,
    MonitoringStatus.SUCCESS: 1,
}


class SmartPlaceAdapter:
    collector_id = "smartplace"
    display_name = "SmartPlace"

    def __init__(
        self,
        repository: QueryRepository,
        *,
        policy: SmartPlacePolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        now = as_utc(self._clock())
        assert now is not None
        return now

    def _stale_cutoff(self) -> datetime | None:
        if self._policy is None:
            return None
        return self._now() - self._policy.max_duration

    def _attempts(self, run_id: str) -> list[CollectorAttempt]:
        return [
            attempt_from_row(row)
            for row in self._repository.fetch_all(
                SMARTPLACE_ATTEMPTS_SQL, (run_id,)
            )
        ]

    def _runs_from_rows(
        self, rows: list[dict[str, object]]
    ) -> list[CollectorRun]:
        attempts_by_run: dict[str, list[CollectorAttempt]] = defaultdict(list)
        if rows:
            run_ids = [str(row["run_id"]) for row in rows]
            attempt_rows = self._repository.fetch_all(
                SMARTPLACE_ATTEMPTS_FOR_RUNS_SQL,
                (json.dumps(run_ids),),
            )
            for attempt_row in attempt_rows:
                attempts_by_run[str(attempt_row["run_id"])].append(
                    attempt_from_row(attempt_row)
                )
        return [
            self._run(row, attempts_by_run.get(str(row["run_id"]), []))
            for row in rows
        ]

    def _run(
        self, row: dict[str, object], attempts: list[CollectorAttempt]
    ) -> CollectorRun:
        scheduled_at = as_utc(row["scheduled_at"])  # type: ignore[arg-type]
        assert scheduled_at is not None
        timezone = ZoneInfo(
            "UTC" if self._policy is None else self._policy.schedule_timezone
        )
        mapped_row = {
            **row,
            "scheduled_date": scheduled_at.astimezone(timezone).date(),
        }
        run = run_from_row(self.collector_id, mapped_row, attempts)
        canonical = row.get("canonical_status")
        authoritative_status = (
            MonitoringStatus(str(canonical))
            if canonical is not None
            else map_raw_status(str(row["raw_status"]))
        )
        run = run.model_copy(
            update={
                "status": authoritative_status,
                # 생산자가 account_key별 결과에서 login을 제외해 확정한 집계다.
                "successful_units": int(row.get("successful_units") or 0),
                "failed_units": int(row.get("failed_units") or 0),
            }
        )
        if (
            self._policy is not None
            and run.status is MonitoringStatus.RUNNING
            and self._now() - run.started_at > self._policy.max_duration
        ):
            return run.model_copy(update={"status": MonitoringStatus.ABORTED})
        return run

    def _scheduled_occurrence(self) -> _ScheduledOccurrence | None:
        if self._policy is None:
            return None
        now = self._now()
        timezone = ZoneInfo(self._policy.schedule_timezone)
        local_now = now.astimezone(timezone)
        today_scheduled_at = datetime.combine(
            local_now.date(), self._policy.daily_scheduled_time, tzinfo=timezone
        )
        occurrence_date = local_now.date()
        if now < today_scheduled_at.astimezone(UTC) + self._policy.start_grace:
            occurrence_date -= timedelta(days=1)
        local_scheduled_at = datetime.combine(
            occurrence_date,
            self._policy.daily_scheduled_time,
            tzinfo=timezone,
        )
        scheduled_at = local_scheduled_at.astimezone(UTC)
        return _ScheduledOccurrence(
            scheduled_at=scheduled_at,
            local_scheduled_at=local_scheduled_at,
            range_start=scheduled_at,
            range_end=scheduled_at + self._policy.attribution_window,
        )

    def _synthetic_missing_runs(
        self,
        occurrence: _ScheduledOccurrence,
        *,
        present: set[str],
    ) -> list[CollectorRun]:
        assert self._policy is not None
        return [
            CollectorRun(
                collector_id=self.collector_id,
                run_id=uuid5(
                    _SYNTHETIC_NAMESPACE,
                    f"{occurrence.scheduled_at.isoformat()}:{scope.scope_id}",
                ),
                scheduled_date=occurrence.local_scheduled_at.date(),
                started_at=occurrence.scheduled_at,
                completed_at=None,
                status=MonitoringStatus.NOT_RUN,
                successful_units=0,
                failed_units=0,
                source_count=None,
                inserted_count=None,
                changed_count=None,
                unchanged_count=None,
                scope_id=scope.scope_id,
                scope_name=scope.scope_name,
            )
            for scope in self._policy.expected_scopes
            if scope.scope_id not in present
        ]

    def _missing_runs(
        self,
        *,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        status: MonitoringStatus | None = None,
    ) -> list[CollectorRun]:
        occurrence = self._scheduled_occurrence()
        if occurrence is None or self._policy is None:
            return []
        if started_from is not None and occurrence.scheduled_at < started_from:
            return []
        if started_to is not None and occurrence.scheduled_at > started_to:
            return []
        if status not in (None, MonitoringStatus.NOT_RUN):
            return []
        rows = self._repository.fetch_all(
            SMARTPLACE_PRESENT_SCOPES_SQL,
            (
                to_sql_datetime(occurrence.range_start),
                to_sql_datetime(occurrence.range_end),
            ),
        )
        present = {str(row["scope_id"]) for row in rows}
        return self._synthetic_missing_runs(occurrence, present=present)

    def latest(self) -> CollectorRun | None:
        occurrence = self._scheduled_occurrence()
        if occurrence is None or self._policy is None:
            runs = self.list_runs(limit=1)
            return runs[0] if runs else None
        rows = self._repository.fetch_all(
            SMARTPLACE_OCCURRENCE_RUNS_SQL,
            (
                to_sql_datetime(self._stale_cutoff()),
                to_sql_datetime(occurrence.range_start),
                to_sql_datetime(occurrence.range_end),
            ),
        )
        expected_ids = {
            scope.scope_id for scope in self._policy.expected_scopes
        }
        latest_by_scope: dict[str, CollectorRun] = {}
        for run in self._runs_from_rows(rows):
            if run.scope_id in expected_ids and run.scope_id not in latest_by_scope:
                assert run.scope_id is not None
                latest_by_scope[run.scope_id] = run
        runs = list(latest_by_scope.values())
        runs.extend(
            self._synthetic_missing_runs(
                occurrence,
                present=set(latest_by_scope),
            )
        )
        if not runs:
            return None
        return max(
            runs,
            key=lambda run: (
                _STATUS_SEVERITY[run.status],
                run.started_at,
                str(run.run_id),
            ),
        )

    def list_runs(
        self,
        *,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        status: MonitoringStatus | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[CollectorRun]:
        synthetic_capacity = (
            0 if self._policy is None else len(self._policy.expected_scopes)
        )
        rows = self._repository.fetch_all(
            SMARTPLACE_LIST_SQL,
            (
                to_sql_datetime(self._stale_cutoff()),
                to_sql_datetime(started_from),
                to_sql_datetime(started_from),
                to_sql_datetime(started_to),
                to_sql_datetime(started_to),
                None if status is None else status.value,
                None if status is None else status.value,
                0,
                offset + limit + synthetic_capacity,
            ),
        )
        runs = self._runs_from_rows(rows)
        if status is not None:
            runs = [run for run in runs if run.status is status]
        runs.extend(
            self._missing_runs(
                started_from=started_from,
                started_to=started_to,
                status=status,
            )
        )
        ordered = sorted(
            runs,
            # 고정 SQL의 동률 순서와 설정된 scope 순서를 그대로 보존한다.
            key=lambda run: run.started_at,
            reverse=True,
        )
        return ordered[offset : offset + limit]

    def count_runs(
        self,
        *,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        status: MonitoringStatus | None = None,
    ) -> int:
        rows = self._repository.fetch_all(
            SMARTPLACE_COUNT_SQL,
            (
                to_sql_datetime(self._stale_cutoff()),
                to_sql_datetime(started_from),
                to_sql_datetime(started_from),
                to_sql_datetime(started_to),
                to_sql_datetime(started_to),
                None if status is None else status.value,
                None if status is None else status.value,
            ),
        )
        persisted = int(rows[0]["total"]) if rows else 0
        return persisted + len(
            self._missing_runs(
                started_from=started_from,
                started_to=started_to,
                status=status,
            )
        )

    def count_runs_by_status(
        self, *, started_from: datetime, started_to: datetime
    ) -> dict[MonitoringStatus, int]:
        rows = self._repository.fetch_all(
            SMARTPLACE_STATUS_COUNTS_SQL,
            (
                to_sql_datetime(self._stale_cutoff()),
                to_sql_datetime(started_from),
                to_sql_datetime(started_to),
            ),
        )
        result = {
            MonitoringStatus(str(row["status"])): int(row["total"])
            for row in rows
        }
        missing = self._missing_runs(
            started_from=started_from,
            started_to=started_to,
        )
        if missing:
            result[MonitoringStatus.NOT_RUN] = (
                result.get(MonitoringStatus.NOT_RUN, 0) + len(missing)
            )
        return result

    def latest_successful_check_at(self) -> datetime | None:
        rows = self._repository.fetch_all(SMARTPLACE_LATEST_SUCCESS_SQL)
        if not rows:
            return None
        return as_utc(rows[0].get("last_successful_check_at"))  # type: ignore[arg-type]

    def get_run(self, run_id: UUID) -> CollectorRun | None:
        rows = self._repository.fetch_all(SMARTPLACE_RUN_SQL, (str(run_id),))
        if rows:
            return self._run(rows[0], self._attempts(str(run_id)))
        for run in self._missing_runs():
            if run.run_id == run_id:
                return run
        return None

    def freshness(self) -> list[FreshnessRecord]:
        return []

    def readiness(self) -> bool:
        return self._repository.ping()
