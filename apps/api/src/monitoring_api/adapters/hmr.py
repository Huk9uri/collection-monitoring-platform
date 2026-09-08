"""HMR 채널 수집 감사·주문 테이블 어댑터다."""

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


_HMR_RUN_COLUMNS = """
    RunId AS run_id,
    ScheduledDate AS scheduled_date,
    StartedAt AS started_at,
    FinishedAt AS completed_at,
    RunStatus AS raw_status,
    SuccessfulChannels AS successful_units,
    FailedChannels AS failed_units
"""

HMR_LATEST_SQL = f"""SELECT TOP (1)
{_HMR_RUN_COLUMNS}
FROM dbo.CHANNEL_COLLECTION_RUN
ORDER BY StartedAt DESC"""

HMR_LIST_SQL = f"""SELECT
{_HMR_RUN_COLUMNS}
FROM dbo.CHANNEL_COLLECTION_RUN
WHERE (? IS NULL OR StartedAt >= ?)
  AND (? IS NULL OR StartedAt <= ?)
ORDER BY StartedAt DESC
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"""

HMR_COUNT_SQL = """SELECT COUNT_BIG(*) AS total
FROM dbo.CHANNEL_COLLECTION_RUN
WHERE (? IS NULL OR StartedAt >= ?)
  AND (? IS NULL OR StartedAt <= ?)"""

HMR_RUN_SQL = f"""SELECT
{_HMR_RUN_COLUMNS}
FROM dbo.CHANNEL_COLLECTION_RUN
WHERE RunId = ?"""

HMR_ATTEMPTS_SQL = """SELECT
    ChannelName AS unit_id,
    ChannelName AS unit_name,
    AttemptNo AS attempt_no,
    StartedAt AS started_at,
    FinishedAt AS completed_at,
    AttemptStatus AS raw_status,
    RecordsCount AS source_count,
    InsertedCount AS inserted_count,
    ChangedCount AS changed_count,
    SkippedCount AS unchanged_count,
    CASE WHEN AttemptStatus IN ('SUCCESS', 'SUCCESS_EMPTY') THEN CAST(1 AS bit)
         ELSE CAST(0 AS bit) END AS committed,
    ErrorCategory AS error_category
FROM dbo.CHANNEL_COLLECTION_ATTEMPT
WHERE RunId = ?
ORDER BY ChannelName, AttemptNo"""

HMR_ATTEMPTS_FOR_RUNS_SQL = """SELECT
    RunId AS run_id,
    ChannelName AS unit_id,
    ChannelName AS unit_name,
    AttemptNo AS attempt_no,
    StartedAt AS started_at,
    FinishedAt AS completed_at,
    AttemptStatus AS raw_status,
    RecordsCount AS source_count,
    InsertedCount AS inserted_count,
    ChangedCount AS changed_count,
    SkippedCount AS unchanged_count,
    CASE WHEN AttemptStatus IN ('SUCCESS', 'SUCCESS_EMPTY') THEN CAST(1 AS bit)
         ELSE CAST(0 AS bit) END AS committed,
    ErrorCategory AS error_category
FROM dbo.CHANNEL_COLLECTION_ATTEMPT
WHERE RunId IN (
    SELECT TRY_CONVERT(uniqueidentifier, [value]) FROM OPENJSON(?)
)
ORDER BY RunId, ChannelName, AttemptNo"""

HMR_FRESHNESS_SQL = """SELECT dataset_id, latest_at
FROM (
    SELECT 1 AS sequence, 'naver' AS dataset_id, MAX(CollectedAt) AS latest_at
    FROM dbo.NAVER_SMARTSTORE_ORDER_ITEM
    UNION ALL SELECT 2, 'godomall', MAX(CollectedAt) FROM dbo.GODOMALL_ORDER_ITEM
    UNION ALL SELECT 3, 'coupang', MAX(CollectedAt) FROM dbo.COUPANG_ORDER_ITEM
    UNION ALL SELECT 4, 'lotteon', MAX(CollectedAt) FROM dbo.LOTTEON_ORDER_ITEM
    UNION ALL SELECT 5, 'elevenst', MAX(CollectedAt) FROM dbo.ELEVENST_ORDER_ITEM
    UNION ALL SELECT 6, 'ssg', MAX(CollectedAt) FROM dbo.SSG_ORDER_ITEM
    UNION ALL SELECT 7, 'cj_onstyle', MAX(CollectedAt) FROM dbo.CJ_ONSTYLE_ORDER_ITEM
    UNION ALL SELECT 8, 'toss', MAX(CollectedAt) FROM dbo.TOSS_SHOPPING_ORDER_ITEM
) AS freshness
ORDER BY sequence"""


class HmrAdapter:
    collector_id = "hmr"
    display_name = "HMR"

    def __init__(self, repository: QueryRepository) -> None:
        self._repository = repository

    def _attempts(self, run_id: str) -> list[CollectorAttempt]:
        rows = self._repository.fetch_all(HMR_ATTEMPTS_SQL, (run_id,))
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
        runs = self._runs(self._repository.fetch_all(HMR_LATEST_SQL))
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
            HMR_LIST_SQL,
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
            HMR_ATTEMPTS_FOR_RUNS_SQL,
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
            HMR_COUNT_SQL,
            (
                to_sql_datetime(started_from),
                to_sql_datetime(started_from),
                to_sql_datetime(started_to),
                to_sql_datetime(started_to),
            ),
        )
        return int(rows[0]["total"]) if rows else 0

    def get_run(self, run_id: str) -> CollectorRun | None:
        runs = self._runs(self._repository.fetch_all(HMR_RUN_SQL, (run_id,)))
        return runs[0] if runs else None

    def freshness(self) -> list[FreshnessRecord]:
        return freshness_from_rows(
            self.collector_id,
            self._repository.fetch_all(HMR_FRESHNESS_SQL),
        )

    def readiness(self) -> bool:
        return self._repository.ping()
