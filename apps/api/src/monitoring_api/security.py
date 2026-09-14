"""비밀번호와 브라우저 세션 비밀값의 단방향 처리."""

import hashlib
import secrets

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode('utf-8')).digest()


SESSION_IDLE_HOURS = 8
SESSION_ABSOLUTE_HOURS = 24
LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_MINUTES = 15


def account_ip_hash(username: str, ip: str) -> bytes:
    # 토큰·비밀번호와 관계없는 정규화 계정/IP 지문. 운영 비밀키 설정을 요구하지 않는다.
    return hashlib.sha256((username.strip().lower() + '\x00' + ip).encode()).digest()
