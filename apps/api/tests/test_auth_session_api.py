from unittest.mock import Mock
from fastapi.testclient import TestClient
from monitoring_api.main import create_app
from monitoring_api.config import Settings
from monitoring_api.security import token_hash


def client(role='admin'):
    app = create_app(Settings(_env_file=None, cors_origins=('https://testserver',),
        auth_audit_key='x' * 32, auth_failure_limit=5, auth_lock_minutes=15, password_min_length=12))
    repository = Mock()
    repository.login.return_value = {'user_id':'u', 'username':'admin', 'role':role}
    repository.authenticate.side_effect = lambda *args: {'session_id':'s', 'user_id':'u', 'username':'admin', 'role':role, 'csrf_hash': token_hash('csrf')}
    app.state.session_repository = repository
    return TestClient(app, base_url='https://testserver'), repository


def test_login_cookie_attributes_and_secret_non_disclosure():
    http, repo = client()
    response = http.post('/api/v1/auth/login', json={'username':'admin','password':'password'}, headers={'Origin':'https://testserver'})
    assert response.status_code == 200
    cookie = response.headers['set-cookie']
    for value in ('HttpOnly', 'Secure', 'SameSite=lax', 'Path=/'):
        assert value in cookie
    assert 'password' not in response.text
    assert len(repo.login.call_args.args[3]) == 32
    assert len(repo.login.call_args.args[4]) == 32
    assert response.headers['cache-control'] == 'no-store'


def test_logout_requires_origin_and_session_bound_csrf():
    http, repo = client()
    http.cookies.set('__Host-monitoring-session', 'token')
    assert http.post('/api/v1/auth/logout').status_code == 403
    assert http.post('/api/v1/auth/logout', headers={'Origin':'https://testserver','X-CSRF-Token':'wrong'}).status_code == 403
    assert http.post('/api/v1/auth/logout', headers={'Origin':'https://testserver','X-CSRF-Token':'csrf'}).status_code == 204
    repo.logout.assert_called_once()


def test_viewer_is_denied_admin_readiness_and_settings_write():
    http, _ = client('viewer')
    http.cookies.set('__Host-monitoring-session', 'token')
    assert http.get('/health/ready').status_code == 403
    assert http.get('/api/v1/settings/history').status_code == 403
    assert http.put('/api/v1/settings/schedules/fcdaum', json={}, headers={'Origin':'https://testserver','X-CSRF-Token':'csrf'}).status_code == 403
    assert http.get('/api/v1/settings/schedules').status_code == 200


def test_expired_or_disabled_session_is_rejected():
    http, repo = client()
    repo.authenticate.side_effect = None
    repo.authenticate.return_value = None
    http.cookies.set('__Host-monitoring-session', 'expired')
    assert http.get('/api/v1/auth/me').status_code == 401


def test_csrf_rotation_accepts_same_origin_get_referer():
    http, repo = client()
    http.cookies.set('__Host-monitoring-session', 'token')
    assert http.get('/api/v1/auth/csrf', headers={'Referer': 'https://testserver/settings/schedules'}).status_code == 200
    repo.rotate_csrf.assert_called_once()
    assert http.get('/api/v1/auth/csrf', headers={'Referer':'https://evil.test'}).status_code == 403


def test_validation_does_not_echo_password_input():
    http, _ = client()
    response = http.post('/api/v1/auth/login', json={'username':'admin', 'password': {'value':'secret-password'}})
    assert response.status_code == 422 and 'secret-password' not in response.text
