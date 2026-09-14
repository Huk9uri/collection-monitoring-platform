from fastapi.testclient import TestClient

from monitoring_api.config import Settings
from monitoring_api.main import create_app


def test_anonymous_monitoring_and_readiness_are_unauthorized():
    client = TestClient(create_app(Settings(_env_file=None)))
    assert client.get('/api/v1/monitoring/collectors').status_code == 401
    assert client.get('/health/ready').status_code == 401
    assert client.get('/api/v1/auth/me').status_code == 401


def test_login_rejects_untrusted_origin_before_database():
    client = TestClient(create_app(Settings(_env_file=None)))
    response = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'secret'}, headers={'Origin': 'https://evil.test'})
    assert response.status_code == 403


def test_login_fails_closed_without_control_database():
    settings = Settings(_env_file=None, cors_origins=('https://testserver',))
    client = TestClient(create_app(settings), base_url='https://testserver')
    response = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'secret'}, headers={'Origin': 'https://testserver'})
    assert response.status_code == 503
    assert 'secret' not in response.text


def test_production_https_and_host_boundary():
    app = create_app(Settings(_env_file=None, production=True,
        allowed_hosts=('testserver',), cors_origins=('https://testserver',)))
    client = TestClient(app, follow_redirects=False)
    assert client.get('/health/live').status_code == 307
    assert client.get('/health/live', headers={'Host': 'evil.test'}).status_code == 400
    secure = TestClient(app, base_url='https://testserver')
    assert secure.get('/health/live').status_code == 200
    for path in ('/docs', '/redoc', '/openapi.json'):
        assert secure.get(path).status_code == 404
