"""SQL Server를 SELECT 전용으로 조회하는 최소 저장소 경계다."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


_WRITE_KEYWORDS = re.compile(
    r"\b(?:INTO|INSERT|UPDATE|DELETE|MERGE|EXEC(?:UTE)?|DROP|ALTER|CREATE|TRUNCATE)\b",
    re.IGNORECASE,
)


def ensure_read_only_connection_string(connection_string: str) -> str:
    """연결 문자열에 SQL Server 읽기 전용 애플리케이션 의도를 강제한다."""

    if not connection_string.strip():
        raise ValueError("DB 연결 문자열이 비어 있습니다.")

    parts = [
        part.strip()
        for part in connection_string.strip().strip(";").split(";")
        if part.strip()
    ]
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
    """고정된 단일 SELECT 문만 실행하고 연결을 즉시 닫는다."""

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
        statement = sql.strip()
        if not statement.upper().startswith("SELECT"):
            raise ValueError("읽기 전용 저장소는 SELECT 문만 허용합니다.")
        without_trailing_separator = statement[:-1] if statement.endswith(";") else statement
        if ";" in without_trailing_separator or _WRITE_KEYWORDS.search(statement):
            raise ValueError("읽기 전용 저장소는 단일 SELECT 문만 허용합니다.")

    def fetch_all(
        self, sql: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        """SELECT 결과를 SQL 별칭 기반 사전 목록으로 반환한다."""

        self._validate_select(sql)
        connection = self._connector(self._connection_string)
        cursor = connection.cursor()
        try:
            if parameters:
                cursor.execute(sql, parameters)
            else:
                cursor.execute(sql)
            columns = [str(description[0]).casefold() for description in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        finally:
            cursor.close()
            connection.close()

    def ping(self) -> bool:
        rows = self.fetch_all("SELECT 1 AS ready")
        return bool(rows and rows[0].get("ready") == 1)
