"""FC다움 감사·업무 테이블을 공통 모니터링 모델로 변환한다."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Protocol

from monitoring_api.adapters.base import (
    CollectorAttempt,
    CollectorRun,
    FreshnessRecord,
    attempt_from_row,
    freshness_from_rows,
    run_from_row,
    to_sql_datetime,
)
from monitoring_api.models import MonitoringStatus


class QueryRepository(Protocol):
    def fetch_all(
        self, sql: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]: ...

    def ping(self) -> bool: ...


_FCDAUM_RUN_COLUMNS = """
    RunId AS run_id,
    ScheduledDate AS scheduled_date,
    StartedAt AS started_at,
    FinishedAt AS completed_at,
    RunStatus AS raw_status,
    SuccessfulBrands AS successful_units,
    FailedBrands AS failed_units
"""

_FCDAUM_RAW_STATUS_SQL = """CASE UPPER(LTRIM(RTRIM(runs.RunStatus)))
    WHEN 'SUCCESS' THEN 'SUCCESS'
    WHEN 'SUCCESS_EMPTY' THEN 'SUCCESS_EMPTY'
    WHEN 'WARNING' THEN 'WARNING'
    WHEN 'PARTIAL' THEN 'PARTIAL_FAILED'
    WHEN 'PARTIAL_FAILED' THEN 'PARTIAL_FAILED'
    WHEN 'FAILED' THEN 'FAILED'
    WHEN 'RUNNING' THEN 'RUNNING'
    WHEN 'ABORTED' THEN 'ABORTED'
    WHEN 'NOT_RUN' THEN 'NOT_RUN'
    ELSE 'FAILED' END"""

_FCDAUM_CANONICAL_STATUS_SQL = f"""CASE
    WHEN {_FCDAUM_RAW_STATUS_SQL} IN ('RUNNING', 'ABORTED', 'NOT_RUN')
        THEN {_FCDAUM_RAW_STATUS_SQL}
    WHEN NOT EXISTS (
        SELECT 1 FROM dbo.FC_DAUM_COLLECTION_ATTEMPT AS attempt
        WHERE attempt.RunId = runs.RunId
    ) THEN {_FCDAUM_RAW_STATUS_SQL}
    WHEN NOT EXISTS (
        SELECT 1 FROM dbo.FC_DAUM_COLLECTION_ATTEMPT AS attempt
        WHERE attempt.RunId = runs.RunId
          AND attempt.AttemptNo = (
              SELECT MAX(latest.AttemptNo)
              FROM dbo.FC_DAUM_COLLECTION_ATTEMPT AS latest
              WHERE latest.RunId = attempt.RunId
                AND latest.BrandCode = attempt.BrandCode
          )
          AND COALESCE(UPPER(LTRIM(RTRIM(attempt.AttemptStatus))), '')
              IN ('SUCCESS', 'SUCCESS_EMPTY')
          AND ISNULL(attempt.DbCommitted, 1) <> 0
    ) THEN 'FAILED'
    WHEN EXISTS (
        SELECT 1 FROM dbo.FC_DAUM_COLLECTION_ATTEMPT AS attempt
        WHERE attempt.RunId = runs.RunId
          AND attempt.AttemptNo = (
              SELECT MAX(latest.AttemptNo)
              FROM dbo.FC_DAUM_COLLECTION_ATTEMPT AS latest
              WHERE latest.RunId = attempt.RunId
                AND latest.BrandCode = attempt.BrandCode
          )
          AND NOT (
              COALESCE(UPPER(LTRIM(RTRIM(attempt.AttemptStatus))), '')
                  IN ('SUCCESS', 'SUCCESS_EMPTY')
              AND ISNULL(attempt.DbCommitted, 1) <> 0
          )
    ) THEN 'PARTIAL_FAILED'
    WHEN EXISTS (
        SELECT 1 FROM dbo.FC_DAUM_COLLECTION_ATTEMPT AS attempt
        WHERE attempt.RunId = runs.RunId
          AND (
              attempt.AttemptNo > 1
              OR NOT (
                  COALESCE(UPPER(LTRIM(RTRIM(attempt.AttemptStatus))), '')
                      IN ('SUCCESS', 'SUCCESS_EMPTY')
                  AND ISNULL(attempt.DbCommitted, 1) <> 0
              )
          )
    ) THEN 'WARNING'
    WHEN NOT EXISTS (
        SELECT 1 FROM dbo.FC_DAUM_COLLECTION_ATTEMPT AS attempt
        WHERE attempt.RunId = runs.RunId
          AND attempt.AttemptNo = (
              SELECT MAX(latest.AttemptNo)
              FROM dbo.FC_DAUM_COLLECTION_ATTEMPT AS latest
              WHERE latest.RunId = attempt.RunId
                AND latest.BrandCode = attempt.BrandCode
          )
          AND ISNULL(attempt.ApiCount, 0) <> 0
    ) THEN 'SUCCESS_EMPTY'
    ELSE 'SUCCESS' END"""

FCDAUM_LATEST_SQL = f"""SELECT TOP (1)
{_FCDAUM_RUN_COLUMNS}
FROM dbo.FC_DAUM_COLLECTION_RUN
ORDER BY StartedAt DESC, CONVERT(char(36), RunId) DESC"""

FCDAUM_LIST_SQL = f"""SELECT
{_FCDAUM_RUN_COLUMNS}
FROM dbo.FC_DAUM_COLLECTION_RUN AS runs
WHERE (? IS NULL OR runs.StartedAt >= ?)
  AND (? IS NULL OR runs.StartedAt <= ?)
  AND (? IS NULL OR {_FCDAUM_CANONICAL_STATUS_SQL} = ?)
ORDER BY StartedAt DESC, CONVERT(char(36), RunId) DESC
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"""

FCDAUM_COUNT_SQL = f"""SELECT COUNT_BIG(*) AS total
FROM dbo.FC_DAUM_COLLECTION_RUN AS runs
WHERE (? IS NULL OR runs.StartedAt >= ?)
  AND (? IS NULL OR runs.StartedAt <= ?)
  AND (? IS NULL OR {_FCDAUM_CANONICAL_STATUS_SQL} = ?)"""

FCDAUM_RUN_SQL = f"""SELECT
{_FCDAUM_RUN_COLUMNS}
FROM dbo.FC_DAUM_COLLECTION_RUN
WHERE RunId = ?"""

FCDAUM_ATTEMPTS_SQL = """SELECT
    BrandCode AS unit_id,
    BrandName AS unit_name,
    AttemptNo AS attempt_no,
    StartedAt AS started_at,
    FinishedAt AS completed_at,
    AttemptStatus AS raw_status,
    ApiCount AS source_count,
    (ReportInsertedCount + IssueInsertedCount + MissionInsertedCount) AS inserted_count,
    (ReportChangedCount + IssueChangedCount + MissionChangedCount) AS changed_count,
    (ReportUnchangedCount + IssueUnchangedCount + MissionUnchangedCount) AS unchanged_count,
    DbCommitted AS committed,
    ErrorCategory AS error_category
FROM dbo.FC_DAUM_COLLECTION_ATTEMPT
WHERE RunId = ?
ORDER BY BrandCode, AttemptNo"""

FCDAUM_ATTEMPTS_FOR_RUNS_SQL = """SELECT
    RunId AS run_id,
    BrandCode AS unit_id,
    BrandName AS unit_name,
    AttemptNo AS attempt_no,
    StartedAt AS started_at,
    FinishedAt AS completed_at,
    AttemptStatus AS raw_status,
    ApiCount AS source_count,
    (ReportInsertedCount + IssueInsertedCount + MissionInsertedCount) AS inserted_count,
    (ReportChangedCount + IssueChangedCount + MissionChangedCount) AS changed_count,
    (ReportUnchangedCount + IssueUnchangedCount + MissionUnchangedCount) AS unchanged_count,
    DbCommitted AS committed,
    ErrorCategory AS error_category
FROM dbo.FC_DAUM_COLLECTION_ATTEMPT
WHERE RunId IN (
    SELECT TRY_CONVERT(uniqueidentifier, [value]) FROM OPENJSON(?)
)
ORDER BY RunId, BrandCode, AttemptNo"""

FCDAUM_FRESHNESS_SQL = """SELECT dataset_id, latest_at
FROM (
    SELECT 1 AS sequence, 'reports' AS dataset_id, MAX(updated_at) AS latest_at
    FROM dbo.fc_daum_qsc_report
    UNION ALL
    SELECT 2, 'issues', MAX(updated_at)
    FROM dbo.fc_daum_qsc_report_issue
    UNION ALL
    SELECT 3, 'missions', MAX(updated_at)
    FROM dbo.fc_daum_mission
) AS freshness
ORDER BY sequence"""


class FcDaumAdapter:
    collector_id = "fcdaum"
    display_name = "FC다움"

    def __init__(self, repository: QueryRepository) -> None:
        self._repository = repository

    def _attempts(self, run_id: str) -> list[CollectorAttempt]:
        rows = self._repository.fetch_all(FCDAUM_ATTEMPTS_SQL, (run_id,))
        return [attempt_from_row(row) for row in rows]

    def _runs(self, rows: list[dict[str, object]]) -> list[CollectorRun]:
        return [
            run_from_row(
                self.collector_id,
                row,
                self._attempts(str(row["run_id"])),
            )
            for row in rows
        ]

    def latest(self) -> CollectorRun | None:
        runs = self._runs(self._repository.fetch_all(FCDAUM_LATEST_SQL))
        return runs[0] if runs else None

    def list_runs(
        self,
        *,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        status: MonitoringStatus | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[CollectorRun]:
        rows = self._repository.fetch_all(
            FCDAUM_LIST_SQL,
            (
                to_sql_datetime(started_from),
                to_sql_datetime(started_from),
                to_sql_datetime(started_to),
                to_sql_datetime(started_to),
                None if status is None else status.value,
                None if status is None else status.value,
                offset,
                limit,
            ),
        )
        if not rows:
            return []
        run_ids = [str(row["run_id"]) for row in rows]
        attempt_rows = self._repository.fetch_all(
            FCDAUM_ATTEMPTS_FOR_RUNS_SQL,
            (json.dumps(run_ids),),
        )
        attempts_by_run: dict[str, list[CollectorAttempt]] = defaultdict(list)
        for attempt_row in attempt_rows:
            attempts_by_run[str(attempt_row["run_id"])].append(
                attempt_from_row(attempt_row)
            )
        return [
            run_from_row(
                self.collector_id,
                row,
                attempts_by_run.get(str(row["run_id"]), []),
            )
            for row in rows
        ]

    def count_runs(
        self,
        *,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        status: MonitoringStatus | None = None,
    ) -> int:
        rows = self._repository.fetch_all(
            FCDAUM_COUNT_SQL,
            (
                to_sql_datetime(started_from),
                to_sql_datetime(started_from),
                to_sql_datetime(started_to),
                to_sql_datetime(started_to),
                None if status is None else status.value,
                None if status is None else status.value,
            ),
        )
        return int(rows[0]["total"]) if rows else 0

    def get_run(self, run_id: str) -> CollectorRun | None:
        runs = self._runs(self._repository.fetch_all(FCDAUM_RUN_SQL, (run_id,)))
        return runs[0] if runs else None

    def freshness(self) -> list[FreshnessRecord]:
        return freshness_from_rows(
            self.collector_id,
            self._repository.fetch_all(FCDAUM_FRESHNESS_SQL),
        )

    def readiness(self) -> bool:
        return self._repository.ping()
