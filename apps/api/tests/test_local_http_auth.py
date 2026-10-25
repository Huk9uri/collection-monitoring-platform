from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from monitoring_api.config import Settings
from monitoring_api.main import create_app
from monitoring_api.security import token_hash


def local_client(host='localhost', origin='http://localhost:5173', production=False):
    app = create_app(Settings(_env_file=None, production=production,
        cors_origins=(origin,), allowed_hosts=(host,)))
    repo = Mock()
    repo.login.return_value = {'user_id': 'u', 'username': 'admin', 'role': 'admin'}
    repo.authenticate.side_effect = lambda *args: {
        'session_id': 's', 'user_id': 'u', 'username': 'admin', 'role': 'admin',
        'csrf_hash': token_hash('csrf'),
    }
    app.state.session_repository = repo
    return TestClient(app, base_url=f'http://{host}:8000', follow_redirects=False), repo


@pytest.mark.parametrize('host', ['localhost', '127.0.0.1'])
def test_local_http_login_restore_and_logout(host):
    origin = f'http://{host}:5173'
    http, repo = local_client(host, origin)
    response = http.post('/api/v1/auth/login', json={'username':'admin','password':'secret'}, headers={'Origin':origin})
    assert response.status_code == 200
    cookie = response.headers['set-cookie']
    assert cookie.startswith('monitoring-dev-session=')
    assert 'Secure' not in cookie and 'HttpOnly' in cookie and 'SameSite=lax' in cookie
    assert http.get('/api/v1/auth/me').status_code == 200
    assert http.get('/api/v1/auth/csrf', headers={'Referer':origin + '/'}).status_code == 200
    assert http.post('/api/v1/auth/logout', headers={'Origin':origin,'X-CSRF-Token':'csrf'}).status_code == 204
    assert http.get('/api/v1/auth/me').status_code == 401
    repo.logout.assert_called_once()


@pytest.mark.parametrize(('host', 'origin'), [
    ('example.test', 'http://localhost:5173'),
    ('localhost', 'http://example.test:5173'),
])
def test_non_local_http_is_rejected_even_if_origin_is_configured(host, origin):
    http, repo = local_client(host, origin)
    assert http.post('/api/v1/auth/login', json={'username':'admin','password':'secret'}, headers={'Origin':origin}).status_code == 403
    repo.login.assert_not_called()


def test_production_does_not_accept_development_cookie():
    http, repo = local_client('localhost', 'https://localhost:5173', production=True)
    http.cookies.set('monitoring-dev-session', 'token')
    assert http.get('/api/v1/auth/me').status_code == 307
    assert http.get('https://localhost:8000/api/v1/auth/me').status_code == 401
    repo.authenticate.assert_not_called()


def test_ipv6_loopback_transport_classification():
    # 설치된 TestClient는 IPv6 netloc를 파싱하지 못하므로 ASGI 요청으로 검사한다.
    from starlette.requests import Request
    from monitoring_api.auth import is_local_http
    http, _ = local_client()
    request = Request({'type':'http', 'scheme':'http', 'path':'/',
        'headers': [(b'host', b'[::1]:8000')], 'app':http.app})
    assert is_local_http(request)


def test_local_password_change_deletes_development_cookie():
    http, repo = local_client()
    http.cookies.set('monitoring-dev-session', 'token', domain='localhost.local', path='/')
    response = http.post('/api/v1/auth/change-password',
        json={'old_password':'old', 'new_password':'new'},
        headers={'Origin':'http://localhost:5173', 'X-CSRF-Token':'csrf'})
    assert response.status_code == 204
    assert response.headers['set-cookie'].startswith('monitoring-dev-session=')
    assert 'Max-Age=0' in response.headers['set-cookie']
    assert http.get('/api/v1/auth/me').status_code == 401
    repo.change_password.assert_called_once()


def test_local_http_preserves_csrf_and_origin_validation():
    http, repo = local_client()
    http.cookies.set('monitoring-dev-session', 'token')
    assert http.post('/api/v1/auth/logout', headers={'Origin':'http://localhost:5173', 'X-CSRF-Token':'wrong'}).status_code == 403
    assert http.post('/api/v1/auth/logout', headers={'Origin':'http://evil.test', 'X-CSRF-Token':'csrf'}).status_code == 403
    repo.logout.assert_not_called()
