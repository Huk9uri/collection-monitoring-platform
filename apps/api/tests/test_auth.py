import pytest
from fastapi import HTTPException, status

from monitoring_api.auth import CurrentUser, get_current_user, require_role
from monitoring_api.models import Role


def test_anonymous_user_is_rejected() -> None:
    from starlette.requests import Request
    with pytest.raises(HTTPException) as error:
        get_current_user(Request({'type': 'http', 'headers': []}))
    assert error.value.status_code == 401


def test_viewer_cannot_pass_operator_role_boundary() -> None:
    operator_only = require_role(Role.OPERATOR)
    viewer = CurrentUser(roles={Role.VIEWER})

    with pytest.raises(HTTPException) as error:
        operator_only(viewer)

    assert error.value.status_code == status.HTTP_403_FORBIDDEN
    assert error.value.detail == "권한이 없습니다."
