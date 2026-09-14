"""제어 연결의 커밋·롤백과 오류 정제 계약."""

import unittest
from types import SimpleNamespace

from monitoring_api.control_db import (
    ControlDatabase, ControlDatabaseUnavailable, build_control_database,
)


class Connection:
    def __init__(self):
        self.events = []
        self.timeout = None

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")

    def close(self):
        self.events.append("close")


class ControlDatabaseTests(unittest.TestCase):
    def test_missing_control_connection_never_falls_back_to_collector(self):
        settings = SimpleNamespace(
            control_connection_string=None, fcdaum_connection_string="Server=collector"
        )
        with self.assertRaises(ControlDatabaseUnavailable):
            build_control_database(settings)

    def make_db(self):
        connection = Connection()
        calls = []

        def connector(value, **options):
            calls.append((value, options))
            return connection

        return ControlDatabase("Server=control", connector=connector), connection, calls

    def test_commit_only_after_success_and_close(self):
        db, connection, calls = self.make_db()
        with db.transaction() as current:
            self.assertIs(current, connection)
            self.assertEqual(connection.events, [])
        self.assertEqual(connection.events, ["commit", "close"])
        self.assertEqual(calls, [("Server=control", {"autocommit": False, "timeout": 5})])
        self.assertEqual(connection.timeout, 30)

    def test_failure_rolls_back_and_closes_without_exposing_details(self):
        db, connection, _ = self.make_db()
        with self.assertRaises(ControlDatabaseUnavailable) as caught:
            with db.transaction():
                raise RuntimeError("password=secret; SQL details")
        self.assertEqual(connection.events, ["rollback", "close"])
        self.assertNotIn("secret", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_connection_failure_is_sanitized(self):
        def fail(*args, **kwargs):
            raise RuntimeError("password=secret")

        db = ControlDatabase("Server=control", connector=fail)
        with self.assertRaisesRegex(ControlDatabaseUnavailable, "제어 DB"):
            with db.transaction():
                self.fail("연결 실패 시 본문이 실행되면 안 된다")

    def test_commit_failure_rolls_back(self):
        db, connection, _ = self.make_db()

        def fail():
            raise RuntimeError("commit failed")

        connection.commit = fail
        with self.assertRaises(ControlDatabaseUnavailable):
            with db.transaction():
                pass
        self.assertEqual(connection.events, ["rollback", "close"])

    def test_missing_configuration_and_invalid_timeouts_rejected(self):
        for value in ("", "   "):
            with self.assertRaises(ValueError):
                ControlDatabase(value)
        for options in ({"connect_timeout_seconds": 0}, {"query_timeout_seconds": -1}):
            with self.assertRaises(ValueError):
                ControlDatabase("Server=control", **options)
