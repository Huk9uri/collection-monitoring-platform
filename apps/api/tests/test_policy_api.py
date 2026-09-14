from unittest.mock import Mock
from test_auth_session_api import client


def test_admin_save_and_conflict_contract():
    http, _ = client()
    http.cookies.set('__Host-monitoring-session', 'token')
    service = Mock()
    http.app.state.policy_service = service
    body = {'timezone_name': 'Asia/Seoul', 'start_grace_minutes': 5,
        'schedule_attribution_window_minutes': 60, 'schedules': [{'weekday_number': 1, 'scheduled_time': '09:00'}],
        'change_reason': '실제 일정 반영', 'version': None}
    service.save.return_value = {'conflict': False, 'latest': {'version': '0000000000000001'}}
    headers = {'Origin':'https://testserver', 'X-CSRF-Token':'csrf'}
    assert http.put('/api/v1/settings/schedules/fcdaum', json=body, headers=headers).status_code == 200
    assert service.save.call_args.args[2] == 'u'
    service.save.return_value = {'conflict': True, 'latest': {'version': '0000000000000002'}}
    response = http.put('/api/v1/settings/schedules/fcdaum', json=body, headers=headers)
    assert response.status_code == 409
    assert response.json()['latest']['version'] == '0000000000000002'


def test_invalid_policy_never_reaches_repository():
    http, _ = client()
    http.cookies.set('__Host-monitoring-session', 'token')
    service = Mock()
    http.app.state.policy_service = service
    response = http.put('/api/v1/settings/schedules/fcdaum', json={'change_reason': '   '},
                        headers={'Origin':'https://testserver', 'X-CSRF-Token':'csrf'})
    assert response.status_code == 422
    service.save.assert_not_called()
