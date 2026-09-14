"""조회자 일정 조회와 관리자 전체 정책 교체."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from monitoring_api.auth import CurrentUser, require_csrf, require_role
from monitoring_api.models import Role
from monitoring_api.services.policy import PolicyUpdate

router = APIRouter(prefix='/api/v1/settings', tags=['settings'])


@router.get('/schedules', dependencies=[Depends(require_role(Role.VIEWER))])
def schedules(request: Request):
    service = request.app.state.policy_service
    return {'items': [{**service.get(key), 'dataset_ids': sorted(service.datasets[key])} for key in service.datasets]}


@router.get('/schedules/{collector_id}', dependencies=[Depends(require_role(Role.VIEWER))])
def schedule(collector_id: str, request: Request):
    try:
        return request.app.state.policy_service.get(collector_id)
    except KeyError:
        raise HTTPException(404, '등록되지 않은 수집기입니다.') from None


@router.put('/schedules/{collector_id}', dependencies=[Depends(require_role(Role.ADMIN))])
def save(collector_id: str, body: PolicyUpdate, request: Request,
         user: Annotated[CurrentUser, Depends(require_csrf)]):
    try:
        result = request.app.state.policy_service.save(collector_id, body, user.user_id)
    except KeyError:
        raise HTTPException(404, '등록되지 않은 수집기입니다.') from None
    except ValueError:
        raise HTTPException(422, '정책 입력 값을 확인하세요.') from None
    if result['conflict']:
        return JSONResponse(status_code=409, content={'detail': '설정이 변경되었습니다. 최신 정책과 비교하세요.', 'latest': result['latest']})
    return result['latest']


@router.get('/history', dependencies=[Depends(require_role(Role.ADMIN))])
def history(request: Request, offset: Annotated[int, Query(ge=0, le=100000)] = 0):
    return {'items': request.app.state.policy_service.repository.history(offset)}
