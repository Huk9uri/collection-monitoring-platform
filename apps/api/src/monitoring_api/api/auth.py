"""HTTPS 쿠키 기반 로그인 API."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr

from monitoring_api.auth import CurrentUser, check_origin, get_current_user, get_session_repository, require_csrf
from monitoring_api.auth import is_local_http, session_cookie_name
from monitoring_api.security import (account_ip_hash, new_token, token_hash,
    SESSION_IDLE_HOURS, SESSION_ABSOLUTE_HOURS, LOGIN_FAILURE_LIMIT, LOGIN_LOCK_MINUTES)

router = APIRouter(prefix='/api/v1/auth', tags=['auth'])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=1, max_length=1024)


class PasswordBody(BaseModel):
    old_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=1, max_length=1024)


def fingerprint(request, username):
    return account_ip_hash(username, request.client.host if request.client else 'unknown')


def public_user(user):
    return {'user_id': user.user_id, 'username': user.username,
            'roles': sorted(user.roles)}


@router.post('/login')
def login(body: LoginBody, request: Request, response: Response):
    check_origin(request)
    token, csrf = new_token(), new_token()
    result = get_session_repository(request).login(
        body.username, body.password.get_secret_value(), fingerprint(request, body.username),
        token_hash(token), token_hash(csrf), datetime.now(UTC).replace(tzinfo=None),
        LOGIN_FAILURE_LIMIT, LOGIN_LOCK_MINUTES, SESSION_IDLE_HOURS, SESSION_ABSOLUTE_HOURS,
    )
    if result is None:
        raise HTTPException(401, '아이디 또는 비밀번호를 확인하세요.')
    response.set_cookie(session_cookie_name(request), token, httponly=True, secure=not is_local_http(request), samesite='lax', path='/',
                        max_age=SESSION_ABSOLUTE_HOURS * 3600)
    return {'user': {'user_id': result['user_id'], 'username': result['username'],
                     'roles': ['viewer', 'admin'] if result['role'] == 'admin' else [result['role']]}, 'csrf_token': csrf}


@router.get('/me')
def me(user: Annotated[CurrentUser, Depends(get_current_user)]):
    return public_user(user)


@router.get('/csrf')
def csrf(request: Request, user: Annotated[CurrentUser, Depends(get_current_user)]):
    # GET은 탐색·cross-site 요청으로 토큰을 무효화하지 못하도록 출처를 검사한다.
    check_origin(request)
    token = new_token()
    get_session_repository(request).rotate_csrf(user.session_id, token_hash(token))
    return {'csrf_token': token}


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response, user: Annotated[CurrentUser, Depends(require_csrf)]):
    get_session_repository(request).logout(user, fingerprint(request, user.username), datetime.now(UTC).replace(tzinfo=None))
    response.delete_cookie(session_cookie_name(request), path='/', secure=not is_local_http(request), httponly=True, samesite='lax')


@router.post('/change-password', status_code=204)
def change_password(body: PasswordBody, request: Request, response: Response,
                    user: Annotated[CurrentUser, Depends(require_csrf)]):
    if not get_session_repository(request).change_password(
        user, body.old_password.get_secret_value(), body.new_password.get_secret_value(),
        fingerprint(request, user.username), datetime.now(UTC).replace(tzinfo=None),
    ):
        raise HTTPException(400, '비밀번호를 변경할 수 없습니다.')
    response.delete_cookie(session_cookie_name(request), path='/', secure=not is_local_http(request), httponly=True, samesite='lax')
