"""MVP의 익명 조회 권한과 향후 인증 교체 지점을 제공한다."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

from monitoring_api.models import Role


class CurrentUser(BaseModel):
    """인증 공급자와 무관하게 사용하는 현재 사용자 표현이다."""

    roles: frozenset[Role]

    def has_role(self, role: Role) -> bool:
        """사용자가 요청된 역할을 보유하는지 반환한다."""

        return role in self.roles


def get_current_user() -> CurrentUser:
    """MVP에서는 인증되지 않은 요청도 조회자 역할로 제한한다."""

    return CurrentUser(roles=frozenset({Role.VIEWER}))


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
