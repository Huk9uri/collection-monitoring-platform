"""서버 세션 인증과 API 역할·CSRF 경계를 제공한다."""

from collections.abc import Callable
from typing import Annotated

from datetime import UTC, datetime
import hmac
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from monitoring_api.control_db import build_control_database
from monitoring_api.repositories.session import SessionRepository
from monitoring_api.security import token_hash, SESSION_IDLE_HOURS

from monitoring_api.models import Role

LOCAL_HOSTS = frozenset({'localhost', '127.0.0.1', '::1'})


def is_local_http(request: Request) -> bool:
    """운영 환경을 제외한 명시적 루프백 HTTP 주소만 허용한다."""
    return (
        not request.app.state.settings.production
        and request.url.scheme == 'http'
        and request.url.hostname in LOCAL_HOSTS
    )


def session_cookie_name(request: Request) -> str:
    return 'monitoring-dev-session' if is_local_http(request) else '__Host-monitoring-session'


class CurrentUser(BaseModel):
    """인증 공급자와 무관하게 사용하는 현재 사용자 표현이다."""

    roles: frozenset[Role]
    user_id: str = ''
    username: str = ''
    session_id: str = ''
    csrf_hash: bytes = Field(default=b'', exclude=True, repr=False)

    def has_role(self, role: Role) -> bool:
        """사용자가 요청된 역할을 보유하는지 반환한다."""

        return role in self.roles


def get_session_repository(request: Request) -> SessionRepository:
    if getattr(request.app.state, 'session_repository', None) is not None:
        return request.app.state.session_repository
    return SessionRepository(build_control_database(request.app.state.settings))


def get_current_user(request: Request) -> CurrentUser:
    if not request.cookies:
        raise HTTPException(401, '로그인이 필요합니다.')
    if request.url.scheme != 'https' and not is_local_http(request):
        raise HTTPException(401, '로그인이 필요합니다.')
    token = request.cookies.get(session_cookie_name(request))
    if not token or len(token) > 128:
        raise HTTPException(401, '로그인이 필요합니다.')
    record = get_session_repository(request).authenticate(
        token_hash(token), datetime.now(UTC).replace(tzinfo=None), SESSION_IDLE_HOURS
    )
    if not record:
        raise HTTPException(401, '로그인이 필요합니다.')
    role = Role(record.pop('role'))
    roles = {role, Role.VIEWER} if role == Role.ADMIN else {role}
    return CurrentUser(roles=roles, **record)


def check_origin(request: Request) -> None:
    origin = request.headers.get('origin')
    if origin is None and request.method == 'GET':
        referer = urlsplit(request.headers.get('referer', ''))
        origin = f'{referer.scheme}://{referer.netloc}'
    if origin not in request.app.state.settings.cors_origins:
        raise HTTPException(403, '허용되지 않은 요청 출처입니다.')
    local_origin = urlsplit(origin).hostname in LOCAL_HOSTS
    if request.url.scheme != 'https' and not (is_local_http(request) and local_origin):
        raise HTTPException(403, '로그인 요청은 HTTPS가 필요합니다.')


def require_csrf(request: Request, user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    check_origin(request)
    token = request.headers.get('x-csrf-token', '')
    if not token or len(token) > 128 or not hmac.compare_digest(token_hash(token), user.csrf_hash):
        raise HTTPException(403, '요청 인증을 갱신한 뒤 다시 시도하세요.')
    return user


def require_role(required_role: Role) -> Callable[[CurrentUser], CurrentUser]:
    """라우트에 사용할 역할 검사 의존성을 생성한다."""

    def check_role(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if not current_user.has_role(required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="권한이 없습니다.",
            )
        return current_user

    return check_role
