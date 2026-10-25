from unittest.mock import Mock
import pytest
from monitoring_api.control_cli import create_user, reset_password
from monitoring_api.control_db import ControlDatabase


def test_initial_user_never_overwrites_existing_account():
    cursor, connection = Mock(), Mock()
    cursor.fetchone.return_value = ('existing',)
    connection.cursor.return_value = cursor
    database = ControlDatabase('Server=test', connector=lambda *a, **kw: connection)
    assert not create_user(database, 'ADMIN', 'password', 'admin', 1)
    assert cursor.execute.call_count == 1
    assert cursor.execute.call_args.args[1] == ('admin',)


def test_password_reset_revokes_sessions_and_audits_in_same_transaction():
    cursor, connection = Mock(), Mock()
    cursor.fetchone.return_value = ('user-id',)
    connection.cursor.return_value = cursor
    database = ControlDatabase('Server=test', connector=lambda *a, **kw: connection)
    assert reset_password(database, 'admin', 'new-password')
    calls = cursor.execute.call_args_list
    assert calls[1].args[1][0].startswith('$argon2id$')
    assert 'UPDATE dbo.monitoring_session' in calls[2].args[0]
    assert 'INSERT INTO dbo.monitoring_auth_audit' in calls[3].args[0]
    connection.commit.assert_called_once()


def test_empty_password_is_rejected_before_db_connection():
    database = Mock()
    with pytest.raises(ValueError):
        create_user(database, 'admin', '', 'admin', 1)
    database.transaction.assert_not_called()
