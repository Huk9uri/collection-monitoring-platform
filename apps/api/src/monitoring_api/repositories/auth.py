"""인증 사용자 조회. 세션 발급과 쓰기는 후속 인증 단계에서 추가한다."""

from dataclasses import dataclass, field

from monitoring_api.control_db import ControlDatabase


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    username: str
    password_hash: str = field(repr=False)
    role: str
    is_active: bool


class AuthRepository:
    def __init__(self, database: ControlDatabase) -> None:
        self._database = database

    def find_user(self, username: str) -> AuthUser | None:
        with self._database.transaction() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "SELECT user_id, username, password_hash, role, is_active "
                    "FROM dbo.monitoring_user WHERE username = ?",
                    (username.strip().lower(),),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return AuthUser(str(row[0]), row[1], row[2], row[3], bool(row[4]))
            finally:
                cursor.close()
