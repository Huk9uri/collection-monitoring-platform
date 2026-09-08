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

FCDAUM_LATEST_SQL = f"""SELECT TOP (1)
{_FCDAUM_RUN_COLUMNS}
FROM dbo.FC_DAUM_COLLECTION_RUN
ORDER BY StartedAt DESC, CONVERT(char(36), RunId) DESC"""

FCDAUM_LIST_SQL = f"""SELECT
{_FCDAUM_RUN_COLUMNS}
FROM dbo.FC_DAUM_COLLECTION_RUN
WHERE (? IS NULL OR StartedAt >= ?)
  AND (? IS NULL OR StartedAt <= ?)
ORDER BY StartedAt DESC, CONVERT(char(36), RunId) DESC
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"""

FCDAUM_COUNT_SQL = """SELECT COUNT_BIG(*) AS total
FROM dbo.FC_DAUM_COLLECTION_RUN
WHERE (? IS NULL OR StartedAt >= ?)
  AND (? IS NULL OR StartedAt <= ?)"""

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
    ) -> int:
        rows = self._repository.fetch_all(
            FCDAUM_COUNT_SQL,
            (
                to_sql_datetime(started_from),
                to_sql_datetime(started_from),
                to_sql_datetime(started_to),
                to_sql_datetime(started_to),
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
