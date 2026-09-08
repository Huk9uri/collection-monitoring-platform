"""SQL Server를 SELECT 전용으로 조회하는 최소 저장소 경계다."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import SqlglotError


def _split_odbc_parts(connection_string: str) -> list[str]:
    """중괄호 값 내부의 세미콜론을 보존해 ODBC 속성을 분리한다."""

    parts: list[str] = []
    current: list[str] = []
    in_braces = False
    index = 0
    while index < len(connection_string):
        character = connection_string[index]
        if character == "{" and not in_braces:
            in_braces = True
            current.append(character)
        elif character == "}" and in_braces:
            if (
                index + 1 < len(connection_string)
                and connection_string[index + 1] == "}"
            ):
                current.extend((character, character))
                index += 1
            else:
                in_braces = False
                current.append(character)
        elif character == "}" and not in_braces:
            raise ValueError("DB 연결 문자열의 중괄호 형식이 올바르지 않습니다.")
        elif character == ";" and not in_braces:
            if part := "".join(current).strip():
                parts.append(part)
            current = []
        else:
            current.append(character)
        index += 1
    if in_braces:
        raise ValueError("DB 연결 문자열의 중괄호 형식이 올바르지 않습니다.")
    if part := "".join(current).strip():
        parts.append(part)
    return parts


def ensure_read_only_connection_string(connection_string: str) -> str:
    """연결 문자열에 SQL Server 읽기 전용 애플리케이션 의도를 강제한다."""

    if not connection_string.strip():
        raise ValueError("DB 연결 문자열이 비어 있습니다.")

    parts = _split_odbc_parts(connection_string.strip().strip(";"))
    intent_indexes: list[int] = []
    for index, part in enumerate(parts):
        key, separator, value = part.partition("=")
        if not separator:
            raise ValueError("DB 연결 문자열 형식이 올바르지 않습니다.")
        if key.strip().casefold() == "applicationintent":
            if value.strip().casefold() != "readonly":
                raise ValueError("ApplicationIntent는 ReadOnly여야 합니다.")
            intent_indexes.append(index)

    if len(intent_indexes) > 1:
        raise ValueError("ApplicationIntent는 한 번만 지정할 수 있습니다.")
    if intent_indexes:
        parts[intent_indexes[0]] = "ApplicationIntent=ReadOnly"
    else:
        parts.append("ApplicationIntent=ReadOnly")
    return ";".join(parts)


def _default_connector(connection_string: str) -> Any:
    try:
        import pyodbc
    except ImportError as exc:  # pragma: no cover - 배포 의존성 누락 경계
        raise RuntimeError("SQL Server 드라이버를 사용할 수 없습니다.") from exc
    return pyodbc.connect(connection_string, autocommit=True)


class ReadOnlyRepository:
    """고정된 단일 SELECT 문만 실행하고 연결을 즉시 닫는다.

    T-SQL AST 검사는 애플리케이션 실수와 비조회 문장을 차단하는 방어 계층이다.
    최종 보안 경계는 데이터 소스마다 DML·DDL 권한이 없는 SELECT 전용 DB
    principal이어야 한다.
    """

    def __init__(
        self,
        connection_string: str,
        *,
        connector: Callable[[str], Any] | None = None,
    ) -> None:
        self._connection_string = ensure_read_only_connection_string(connection_string)
        self._connector = connector or _default_connector

    @staticmethod
    def _validate_select(sql: str) -> None:
        try:
            statements = parse(sql, read="tsql")
        except SqlglotError as exc:
            raise ValueError(
                "읽기 전용 저장소는 하나의 SELECT 조회만 허용합니다."
            ) from exc
        if len(statements) != 1 or not isinstance(statements[0], exp.Query):
            raise ValueError("읽기 전용 저장소는 하나의 SELECT 조회만 허용합니다.")
        statement = statements[0]
        if statement.find(exp.Into) or statement.find(exp.NextValueFor):
            raise ValueError("읽기 전용 저장소는 하나의 SELECT 조회만 허용합니다.")

    def fetch_all(
        self, sql: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        """SELECT 결과를 SQL 별칭 기반 사전 목록으로 반환한다."""

        self._validate_select(sql)
        connection = self._connector(self._connection_string)
        try:
            cursor = connection.cursor()
            try:
                if parameters:
                    cursor.execute(sql, parameters)
                else:
                    cursor.execute(sql)
                columns = [
                    str(description[0]).casefold()
                    for description in cursor.description
                ]
                return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
            finally:
                cursor.close()
        finally:
            connection.close()

    def ping(self) -> bool:
        rows = self.fetch_all("SELECT 1 AS ready")
        return bool(rows and rows[0].get("ready") == 1)
