from __future__ import annotations

from typing import Any

import pytest

from monitoring_api.db import ReadOnlyRepository


class Cursor:
    description = [("ready",)]

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.closed = False

    def execute(self, _: str) -> None:
        if self.fail:
            raise TimeoutError("statement deadline")

    def fetchall(self) -> list[tuple[int]]:
        return [(1,)]

    def close(self) -> None:
        self.closed = True


class Connection:
    def __init__(self, cursor: Cursor) -> None:
        self._cursor = cursor
        self.timeout = 0
        self.closed = False

    def cursor(self) -> Cursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True


def test_repository_applies_connect_and_statement_timeouts() -> None:
    cursor = Cursor()
    connection = Connection(cursor)
    connector_calls: list[tuple[str, int]] = []

    def connector(connection_string: str, *, timeout: int) -> Any:
        connector_calls.append((connection_string, timeout))
        return connection

    repository = ReadOnlyRepository(
        "Driver={ODBC Driver 18 for SQL Server};Server=db",
        connector=connector,
        connect_timeout_seconds=4,
        query_timeout_seconds=9,
    )

    assert repository.ping() is True
    assert connector_calls[0][1] == 4
    assert connection.timeout == 9
    assert cursor.closed is True
    assert connection.closed is True


def test_repository_cleans_up_after_statement_timeout() -> None:
    cursor = Cursor(fail=True)
    connection = Connection(cursor)
    repository = ReadOnlyRepository(
        "Driver={ODBC Driver 18 for SQL Server};Server=db",
        connector=lambda _connection_string, *, timeout: connection,
        connect_timeout_seconds=1,
        query_timeout_seconds=2,
    )

    with pytest.raises(TimeoutError, match="deadline"):
        repository.ping()

    assert cursor.closed is True
    assert connection.closed is True
