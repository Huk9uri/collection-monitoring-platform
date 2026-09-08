# Task 2 구현 보고서: FastAPI 공통 모델, 설정과 인증 경계

## 변경 파일

- `apps/api/pyproject.toml`: FastAPI, Pydantic Settings와 API 테스트 선택 의존성을 선언하고 pytest 경고 필터를 추가했다.
- `apps/api/src/monitoring_api/config.py`: `MONITORING_CORS_ORIGINS`를 읽는 설정 모델과 캐시된 설정 조회 함수를 추가했다.
- `apps/api/src/monitoring_api/models.py`: 여덟 `MonitoringStatus`, 역할, 상태 심각도와 UTC 시각 범위 모델을 추가했다.
- `apps/api/src/monitoring_api/auth.py`: 익명 `viewer` 기본 사용자와 역할 검사 의존성을 추가했다.
- `apps/api/src/monitoring_api/main.py`: GET/Authorization CORS 경계와 DB 비의존 라이브 상태 확인 엔드포인트를 추가했다.
- `apps/api/tests/test_models.py`: 상태 계약, 부분 실패 장애 심각도, UTC 시각 검증을 추가했다.
- `apps/api/tests/test_auth.py`: 익명 사용자의 viewer 전용 권한과 operator 거부를 추가했다.
- `apps/api/tests/test_health.py`: 라이브 상태 확인과 CORS 허용·거부 경계를 추가했다.
- `README.md`: API와 API 테스트 선택 의존성의 재현 가능한 설치 명령으로 갱신했다.

## 테스트 및 결과

```powershell
# Task 2 테스트
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_models.py apps/api/tests/test_auth.py apps/api/tests/test_health.py -q -p no:cacheprovider
# 결과: 10 passed

# 전체 API 테스트
$apiVenvScripts = (Resolve-Path 'apps/api/.venv/Scripts').Path
$env:Path = "$apiVenvScripts;$env:Path"
$env:PYTEST_ADDOPTS = '-p no:cacheprovider'
npm run test:api
# 결과: 11 passed

# 문법 검사
apps/api/.venv/Scripts/python.exe -m compileall -q apps/api/src apps/api/tests
# 결과: 성공
```

## 자체 검토

- `MonitoringStatus`는 명세의 여덟 값을 순서와 대소문자까지 그대로 노출한다.
- `PARTIAL_FAILED`와 `FAILED`, `ABORTED`를 `INCIDENT`로 매핑해 부분 실패를 주의 상태로 낮추지 않는다.
- 실행 시각은 naive 시각과 UTC 이외 오프셋을 거부하고 UTC로 정규화한다.
- 익명 요청은 오직 `viewer` 역할만 가지며 `require_role(Role.OPERATOR)`은 403을 반환한다.
- CORS는 설정 Origin, `GET`, 명시적 `Authorization`만 구성했다. 브라우저의 CORS 안전 목록 헤더는 Starlette가 함께 처리하지만 임의의 `X-API-Key`는 거부한다.
- 라이브 상태 확인은 DB나 어댑터를 생성·조회하지 않는다.

## 우려사항

- 현재 C: 드라이브의 여유 공간이 약 1.1GB여서 pytest 기본 캐시 쓰기는 `No space left on device`로 실패했다. 캐시 공급자를 비활성화한 동일 전체 테스트는 11개 모두 통과했다. 구현 코드와 테스트 결과에는 영향이 없지만 작업공간 용량 정리가 필요하다.
