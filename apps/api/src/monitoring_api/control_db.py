"""인증·정책 전용 연결 경계. 수집기 SELECT 전용 연결과 별도로 사용한다."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any


class ControlDatabaseUnavailable(RuntimeError):
    """외부에 원문 DB 오류를 전달하지 않는 장애 코드."""


def build_control_database(settings: Any) -> "ControlDatabase":
    """전용 설정만 사용하며 수집 DB 연결로 fallback하지 않는다."""
    secret = settings.control_connection_string
    if secret is None or not secret.get_secret_value().strip():
        raise ControlDatabaseUnavailable("제어 DB 연결 설정이 필요합니다.")
    return ControlDatabase(
        secret.get_secret_value(),
        connect_timeout_seconds=settings.db_connect_timeout_seconds,
        query_timeout_seconds=settings.db_query_timeout_seconds,
    )


def _connect(connection_string: str, **options: Any) -> Any:
    import pyodbc

    return pyodbc.connect(connection_string, **options)


class ControlDatabase:
    """고정 SQL repository에서만 사용하는 명시적 트랜잭션 연결 팩토리.

    최종 권한 경계는 제어 테이블에만 최소 권한을 가진 DB 계정이다.
    이 객체는 임의 SQL 실행 API를 제공하지 않는다.
    """

    def __init__(
        self,
        connection_string: str,
        *,
        connector: Callable[..., Any] | None = None,
        connect_timeout_seconds: int = 5,
        query_timeout_seconds: int = 30,
    ) -> None:
        if not connection_string.strip():
            raise ValueError("제어 DB 연결 설정이 필요합니다.")
        if connect_timeout_seconds <= 0 or query_timeout_seconds <= 0:
            raise ValueError("DB timeout은 양수여야 합니다.")
        self._connection_string = connection_string
        self._connector = connector or _connect
        self._connect_timeout = connect_timeout_seconds
        self._query_timeout = query_timeout_seconds

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        connection = None
        try:
            connection = self._connector(
                self._connection_string, autocommit=False, timeout=self._connect_timeout
            )
            connection.timeout = self._query_timeout
            yield connection
            connection.commit()
        except BaseException as exc:
            if connection is not None:
                try:
                    connection.rollback()
                except Exception:
                    pass
            if not isinstance(exc, Exception):
                raise
            raise ControlDatabaseUnavailable("제어 DB 요청을 처리할 수 없습니다.") from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
