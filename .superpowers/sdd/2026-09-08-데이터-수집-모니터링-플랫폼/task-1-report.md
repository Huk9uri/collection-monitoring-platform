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

## Fix round 1: 품질 검토 반영

### 변경

- 루트 `package.json`의 Node.js 최소 버전을 Vite 7.3.6 요구사항과 일치하는
  `>=22.12.0`으로 올렸다.
- `test:api`는 운영체제별 `.venv/Scripts` 경로 대신, 활성화한 가상환경의
  `python -m pytest`를 사용하도록 바꿨다.
- 웹 `lint` 명령을 TypeScript 타입 검사에서 `eslint . --max-warnings=0`으로
  교체하고 `apps/web/eslint.config.js` 및 ESLint TypeScript 설정을 추가했다.
- `vite`와 `@vitejs/plugin-react`를 웹 런타임 의존성에서 개발 의존성으로
  옮기고 잠금 파일을 갱신했다.
- README에 Node.js 최소 버전과 Windows/macOS/Linux별 API 가상환경 활성화
  절차를 기록했다.

### Covering test 파일

- `apps/api/tests/test_package.py`: 활성화한 Python 3.12 가상환경에서 API
  패키지 import를 검증한다.
- `apps/web/src/app.test.tsx`: Vitest로 웹 앱의 모니터링 제목 렌더링을
  검증한다.

### 실행 명령과 결과

| 명령 | 결과 |
| --- | --- |
| `npm test` | 통과: Vitest 1개 |
| `npm run test:api` | 통과: 활성화한 API 가상환경에서 pytest 1개 |
| `npm run lint` | 통과: ESLint 경고 0개 |
| `npm run typecheck` | 통과 |
| `npm run build` | 통과: Vite 프로덕션 빌드 생성 |

### Self-review

- Node.js 제약은 설치된 Vite 7.3.6의 `>=22.12.0` 요구사항과 일치한다.
- API 테스트 명령은 Windows, macOS, Linux 모두에서 활성화한 가상환경의
  `python`을 사용하므로 운영체제 전용 실행 파일 경로를 포함하지 않는다.
- `lint`는 이제 ESLint가 실제 TypeScript/TSX/Vite 설정 파일을 검사하고,
  `typecheck`는 별도 TypeScript 컴파일 검증을 유지한다.
- Vite와 React 플러그인은 빌드·개발에만 필요하므로 `devDependencies`에
  있으며, 브라우저 런타임 의존성은 React와 React DOM만 남는다.
- 기존 미커밋 구현계획 문서는 수정하거나 스테이징하지 않는다.

## Fix round 2: Node.js 버전 계약 정렬

### 변경

- 루트 `package.json`의 Node.js 최소 버전을 ESLint 10.10.0의 Node 22 지원
  최소 버전과 일치하도록 `>=22.13.0`으로 올렸다.
- `package-lock.json`의 루트 패키지 엔진 메타데이터를 같은 값으로 갱신했다.
- README의 로컬 개발 사전 요구사항을 Node.js 22.13.0 이상으로 변경했다.

### Covering test 파일

- `apps/api/tests/test_package.py`: 활성화한 Python 3.12 가상환경에서 API
  패키지 import를 검증한다.
- `apps/web/src/app.test.tsx`: Vitest로 웹 앱의 모니터링 제목 렌더링을
  검증한다.

### 실행 명령과 결과

| 명령 | 결과 |
| --- | --- |
| `npm test` | 통과: Vitest 1개 |
| `npm run test:api` | 통과: 활성화한 API 가상환경에서 pytest 1개 |
| `npm run lint` | 통과: ESLint 경고 0개 |
| `npm run typecheck` | 통과 |
| `npm run build` | 통과: Vite 프로덕션 빌드 생성 |

### Self-review

- Vite 7.3.6은 Node.js 22.12.0 이상을 요구하지만, ESLint 10.10.0은
  Node.js 22.13.0 이상을 요구한다. 둘 중 더 엄격한 `>=22.13.0`을 루트
  패키지, 잠금 파일, README에 동일하게 적용했다.
- 이 수정은 Node 런타임 계약과 문서·잠금 파일의 정합성만 변경하며, 기존
  API·웹 테스트와 공통 명령의 동작은 유지한다.
- 기존 미커밋 구현계획 문서는 수정하거나 스테이징하지 않는다.
