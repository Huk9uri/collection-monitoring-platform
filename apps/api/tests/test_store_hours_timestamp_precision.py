from datetime import datetime

import pytest

from monitoring_api.adapters.naver_store_hours import parse_run
from test_naver_store_hours_adapter import row


def test_sql_millisecond_truncation_preserves_payload_precision():
    record = row(started_at='2026-09-10T01:00:00.553809Z',
                 completed_at='2026-09-10T02:00:00.569689Z')
    record['started_at'] = datetime(2026, 9, 10, 1, microsecond=553000)
    record['completed_at'] = datetime(2026, 9, 10, 2, microsecond=569000)
    run = parse_run(record)
    assert run.started_at.microsecond == 553809
    assert run.completed_at.microsecond == 569689


@pytest.mark.parametrize('sql_microsecond', [552000, 553001, 554000])
def test_actual_time_mismatch_is_not_accepted_as_rounding(sql_microsecond):
    record = row(started_at='2026-09-10T01:00:00.553809Z')
    record['started_at'] = datetime(2026, 9, 10, 1, microsecond=sql_microsecond)
    with pytest.raises(ValueError, match='시각'):
        parse_run(record)


def test_exact_microsecond_match_is_still_accepted():
    record = row(started_at='2026-09-10T01:00:00.553809Z')
    record['started_at'] = datetime(2026, 9, 10, 1, microsecond=553809)
    assert parse_run(record).started_at.microsecond == 553809


def test_missing_sql_completion_is_not_accepted():
    record = row()
    record['completed_at'] = None
    with pytest.raises(ValueError, match='시각'):
        parse_run(record)
