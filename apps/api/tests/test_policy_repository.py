from datetime import datetime
from unittest.mock import Mock
import pytest
from monitoring_api.control_db import ControlDatabase, ControlDatabaseUnavailable
from monitoring_api.repositories.policy import PolicyRepository
from monitoring_api.services.policy import PolicyUpdate


def update(version=None):
    return PolicyUpdate(timezone_name='Asia/Seoul', start_grace_minutes=5,
        schedule_attribution_window_minutes=60, schedules=[{'weekday_number': 1, 'scheduled_time': '09:00'}],
        change_reason='실제 일정 반영', version=version)


def test_audit_failure_rolls_back_policy_and_schedule_writes():
    cursor, connection = Mock(), Mock()
    connection.cursor.return_value = cursor
    cursor.fetchone.side_effect = [None, ('Asia/Seoul', None, 5, 60, True, bytes(8), datetime(2026,9,14))]
    cursor.fetchall.side_effect = [[(1, '09:00', True)], []]
    def execute(sql, parameters):
        if 'INSERT INTO dbo.monitoring_policy_history' in sql:
            raise RuntimeError('secret SQL audit failure')
    cursor.execute.side_effect = execute
    repository = PolicyRepository(ControlDatabase('Server=test', connector=lambda *a, **kw: connection))
    with pytest.raises(ControlDatabaseUnavailable):
        repository.save('fcdaum', update(), 'user-id')
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert any('INSERT INTO dbo.monitoring_collector_policy' in sql for sql in statements)
    assert any('INSERT INTO dbo.monitoring_policy_history' in sql for sql in statements)


def test_version_conflict_performs_no_write():
    cursor, connection = Mock(), Mock()
    connection.cursor.return_value = cursor
    cursor.fetchone.return_value = ('Asia/Seoul', None, 5, 60, True, bytes.fromhex('0000000000000001'), datetime(2026,9,14))
    cursor.fetchall.side_effect = [[(1, '09:00', True)], []]
    repository = PolicyRepository(ControlDatabase('Server=test', connector=lambda *a, **kw: connection))
    result = repository.save('fcdaum', update('0000000000000002'), 'user-id')
    assert result['conflict']
    assert result['latest']['version'] == '0000000000000001'
    assert all(call.args[0].startswith('SELECT') for call in cursor.execute.call_args_list)
