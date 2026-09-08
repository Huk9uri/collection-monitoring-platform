# Task 1 구현 보고서: 모노레포 기반과 공통 개발 명령

## 변경 파일

- 루트: `package.json`, `package-lock.json`, `.editorconfig`, `.env.example`,
  `README.md`
- API: `apps/api/pyproject.toml`,
  `apps/api/src/monitoring_api/__init__.py`,
  `apps/api/tests/test_package.py`
- 웹: `apps/web/package.json`, `apps/web/tsconfig.json`,
  `apps/web/tsconfig.app.json`, `apps/web/tsconfig.node.json`,
  `apps/web/vite.config.ts`, `apps/web/index.html`, `apps/web/src/main.tsx`,
  `apps/web/src/app.tsx`, `apps/web/src/app.test.tsx`

## 테스트 우선 구현 기록

1. `test_package.py`를 먼저 작성하고 Python 3.12 가상환경에서 실행했다.
   `ModuleNotFoundError: No module named 'monitoring_api'`로 실패를 확인했다.
2. `app.test.tsx`를 먼저 작성하고 Vite/Vitest 의존성을 설치한 뒤 실행했다.
   `./app` 모듈을 찾지 못해 실패하는 것을 확인했다.
3. 최소 API 패키지와 React 앱을 추가한 뒤 두 테스트를 통과시켰다.

## 실행한 검증 명령과 결과

| 명령 | 결과 |
| --- | --- |
| `npm run test:api` | 통과: pytest 1개 |
| `npm test` | 통과: Vitest 1개 |
| `npm run lint` | 통과 |
| `npm run typecheck` | 통과 |
| `npm run build` | 통과: Vite 프로덕션 빌드 생성 |

## Self-review

- 루트 `test`, `lint`, `build` 명령은 `@collection-monitoring/web` 워크스페이스에
  위임되고, `test:api`는 `apps/api/.venv`의 pytest를 실행한다.
- API 테스트는 실제 패키지 import를 검증하며, 웹 테스트는 실제 렌더링 결과의
  제목을 검증한다.
- 환경 예시는 로컬 URL만 포함하고 비밀값은 포함하지 않는다.
- README와 이 보고서는 한국어로 작성했다.
- 기존의 미커밋 구현계획 문서 변경은 수정하거나 스테이징하지 않았다.

## 우려사항

- 현재 CI 구성은 후속 작업에서 추가해야 한다. 이 작업은 로컬 공통 명령과
  최소 앱 기반만 구성한다.
