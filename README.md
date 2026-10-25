# Collection Monitoring Platform

여러 데이터 수집기의 **실행 결과·적재 현황·데이터 신선도**를 한곳에서 확인하는 운영 모니터링 대시보드입니다.

수집기마다 다른 감사 테이블과 상태를 FastAPI 어댑터에서 공통 모델로 정규화하고,
React 웹에서 실행 이력과 장애 상태를 일관되게 제공합니다. 수집기 DB에는 SELECT 전용으로
연결하며, 인증과 모니터링 기준 일정은 별도 제어 DB에서 관리합니다.

## 해결하는 문제

수집 프로세스가 종료되었다고 해서 필요한 데이터가 정상적으로 적재되었거나 최신 상태라는
뜻은 아닙니다. 운영자는 수집기마다 다른 로그와 테이블을 확인해야 하고, 일부 실패와
미실행을 구분하기도 어렵습니다.

이 프로젝트는 실행 결과와 데이터 신선도를 함께 보여주고, 예약 시각·허용 실행시간·신선도
SLA를 기준으로 현재 상태를 판단해 운영자가 확인할 대상을 좁힐 수 있도록 합니다.

## 주요 기능

- **상태 요약:** 오늘의 실행 결과와 수집기별 현재 상태 확인
- **실행 이력:** 수집기·기간·상태별 조회, 페이지 탐색 및 시도 상세 확인
- **데이터 신선도:** 마지막 성공 확인 시각과 실제 데이터 변경 시각 구분
- **부분 장애 표시:** 일부 소스 조회가 실패해도 정상 소스 결과와 실패 현황 제공
- **인증과 권한:** 아이디·비밀번호 로그인, 쿠키 세션, viewer/admin 역할별 접근 제어
- **기준 일정 관리:** 관리자의 판정 기준 변경과 변경 이력 조회

화면은 최초 조회와 사용자의 새로고침으로 갱신합니다. 수집 실행·재실행·삭제 기능은
제공하지 않습니다. 기준 일정 변경은 모니터링 판정에 적용되며 실제 작업 스케줄러를
변경하지 않습니다.

### 지원 수집기

| 어댑터 | 모니터링 대상 |
| --- | --- |
| `fcdaum` | FC다움 수집 실행·시도 이력 및 데이터 신선도 |
| `hmr` | HMR 채널별 수집 실행·시도 이력 및 데이터 신선도 |
| `smartplace` | SmartPlace 브랜드별 실행 및 수집 유형별 시도 |
| `naver-store-hours` | 네이버 매장 영업시간 실행, 검토·실패 및 대상 커버리지 |
| `naver-review` | 네이버 방문자·블로그 리뷰 실행·시도 및 데이터 신선도 |

각 어댑터는 해당 수집기의 감사·업무 테이블을 전제로 합니다. 연결 방법과 필요한
테이블은 [운영 문서](docs/운영/로컬-실행.md) 및 수집기별 문서를 참고하세요.

## 핵심 설계

```text
React 웹
   │ 공통 HTTP API
FastAPI ── 인증·정책 저장소 ── 제어 DB (사용자·세션·기준 일정·감사 이력)
   │
모니터링 서비스 (상태 판정·신선도·부분 장애 처리)
   │
수집기별 어댑터 (공통 모델로 정규화)
   │ SELECT 전용
수집기 DB (감사·업무 테이블)
```

- **스키마 격리:** 수집기별 차이는 API 어댑터에서 처리하고, 웹은 공통 API 계약만 사용합니다.
- **판정 분리:** 저장된 실행 결과와 현재 시점의 일정·신선도 판정을 구분합니다.
  현재 상태는 `NOT_RUN`, 장시간 실행의 `ABORTED`, 신선도 `WARNING` 등을 반영합니다.
- **장애 격리:** 소스별 동시 작업 수와 응답 제한 시간을 두어 지연이 다른 소스로 번지는 것을 제한합니다.
- **권한 분리:** 수집기 DB는 SELECT 전용 계정을 사용하고, 제어 DB에만 인증·정책 관련 쓰기를 수행합니다.
- **오류 응답 제한:** 연결 문자열·SQL 원문·원문 예외를 API 오류 응답에 포함하지 않습니다.

공통 상태는 `SUCCESS`, `SUCCESS_EMPTY`, `WARNING`, `PARTIAL_FAILED`, `FAILED`,
`RUNNING`, `ABORTED`, `NOT_RUN`입니다. `PARTIAL_FAILED`는 화면에서 부분 실패로
표시하는 장애 상태입니다.

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| 웹 | React 19, TypeScript, Vite, TanStack Query, Tailwind CSS, Radix UI |
| API | Python 3.12, FastAPI, Pydantic, pyodbc |
| 데이터베이스 | SQL Server, Microsoft ODBC Driver |
| 검증 | Vitest, Testing Library, pytest, ESLint, TypeScript |

웹과 API는 모노레포에서 계약과 변경 이력을 공유하며, 독립된 프로세스로 실행·배포합니다.

## 시작하기

### 준비물과 실행 범위

- Node.js 22.13.0 이상, Python 3.12 64비트
- 연결 대상에 맞는 Microsoft ODBC Driver 17 또는 18 for SQL Server
- 수집기 감사·업무 테이블과 SELECT 전용 계정
- 인증·정책용 제어 DB, 제어 테이블 및 사용자 계정

테스트는 fixture/mock 기반으로 실행할 수 있지만 실제 화면의 로그인과 데이터 조회에는
DB 준비가 필요합니다. DB 연결 없이 API의 `/health/live` 생존 검사는 가능합니다.

### 의존성 설치

저장소 루트에서 실행합니다.

```powershell
npm ci
py -3.12 -m venv apps/api/.venv
apps/api/.venv/Scripts/python.exe -m pip install -e "apps/api[test]"
```

macOS/Linux에서는 Python 가상환경을 다음과 같이 준비합니다.

```bash
python3.12 -m venv apps/api/.venv
apps/api/.venv/bin/python -m pip install -e "apps/api[test]"
```

### 환경과 DB 준비

1. 루트의 `.env.example`을 참고해 `.env`를 작성합니다. 예제 연결 문자열은 실제 접속 정보가
   아니므로 그대로 사용하지 말고, 사용할 소스만 설정합니다.
2. 수집기마다 전용 조회 계정을 설정합니다. 수집기 연결 문자열에는
   `ApplicationIntent=ReadOnly`를 사용하며 실제 DB 권한도 SELECT 전용으로 제한합니다.
3. [제어 DB 적용 절차](docs/운영/제어-DB-스키마-적용.md)에 따라 별도 제어 DB를 준비하고
   `MONITORING_CONTROL_CONNECTION_STRING`을 설정합니다.
4. [로그인 운영 문서](docs/운영/로그인-및-기준-일정.md)에 따라 CLI로 최초 사용자를 생성합니다.
5. `apps/web/.env.local`에 `VITE_MONITORING_API_URL=http://localhost:8000`을 설정하고,
   API의 `MONITORING_CORS_ORIGINS`를 `http://localhost:5173`으로 맞춥니다.

예약 시각과 SLA는 실제 운영 기준을 확인한 값만 입력합니다. 상세 변수와 소스별 준비 절차는
[로컬 실행 문서](docs/운영/로컬-실행.md)를 참고하세요. 실제 비밀번호와 연결 문자열은
커밋하지 않습니다.

### API와 웹 실행

Windows PowerShell에서 터미널 두 개를 사용합니다.

```powershell
# 터미널 1: 저장소 루트에서 API 실행
apps/api/.venv/Scripts/python.exe -m uvicorn monitoring_api.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
```

```powershell
# 터미널 2: 웹 실행
npm run dev --workspace=@collection-monitoring/web
```

macOS/Linux에서는 API 명령의 Python 경로를 `apps/api/.venv/bin/python`으로 바꿉니다.
웹은 `http://localhost:5173`, API는 `http://localhost:8000`으로 접속합니다.
로그인 쿠키가 전달되도록 브라우저에서 사용하는 호스트 이름을 동일하게 맞춥니다.

개발 환경 API 문서는 `http://localhost:8000/docs`에서 확인할 수 있습니다.
`/health/live`는 공개 생존 검사이며, `/health/ready`는 관리자 인증이 필요합니다.
인증된 readiness 요청에서 등록된 소스가 없거나 소스가 준비되지 않았으면 503을 반환합니다.
운영 배포는 같은 사이트의 HTTPS 구성과 정확한 허용 Origin·Host 설정을 전제로 합니다.

## 검증

```powershell
npm test
npm run lint
npm run typecheck
npm run build
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests
```

macOS/Linux에서는 마지막 명령의 Python 경로를 `apps/api/.venv/bin/python`으로 바꿉니다.
API 가상환경을 활성화한 경우에는 `npm run test:api`도 사용할 수 있습니다.
테스트 성공은 실제 SQL Server 연결·배포 검증을 대신하지 않습니다.

## 저장소 구조

```text
apps/
├─ web/                     # React 웹과 컴포넌트 테스트
└─ api/
   ├─ src/monitoring_api/   # HTTP API, 어댑터, 서비스, 저장소
   ├─ tests/               # API·상태 판정·DB 경계 테스트
   └─ sql/                 # 제어 DB 생성·검증 스크립트
docs/
├─ 설계/
├─ 구현계획/
└─ 운영/
```

## 상세 문서

- [로컬 실행](docs/운영/로컬-실행.md)
- [로그인 및 기준 일정 관리](docs/운영/로그인-및-기준-일정.md)
- [제어 DB 스키마 적용](docs/운영/제어-DB-스키마-적용.md)
- [배포 및 장애 대응](docs/운영/배포-및-장애대응.md)
- [SmartPlace 모니터링](docs/운영/smartplace-사후-모니터링.md)
- [네이버 영업시간 모니터링](docs/운영/naver-store-hours-사후-모니터링.md)
- [네이버 리뷰 모니터링](docs/운영/naver-review-사후-모니터링.md)

일부 운영 문서는 별도 수집기 저장소의 SQL·계측 코드와 내부 환경을 참조합니다.


