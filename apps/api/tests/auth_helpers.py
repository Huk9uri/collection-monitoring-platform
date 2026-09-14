"""조회 계약 테스트에서만 사용하는 명시적 인증 사용자 앱 팩토리."""
from monitoring_api.main import create_app
from monitoring_api.auth import get_current_user, CurrentUser
from monitoring_api.config import Settings


def create_admin_app(*args, **kwargs):
    if not args and 'settings' not in kwargs:
        kwargs['settings'] = Settings(_env_file=None)
    app = create_app(*args, **kwargs)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(roles={'viewer', 'admin'})
    return app
