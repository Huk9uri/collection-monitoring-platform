# Collection Monitoring Platform

FC다움, HMR, SmartPlace 및 향후 추가될 데이터 수집기의 실행·적재·신선도를 한곳에서
확인하기 위한 사내 운영 모니터링 플랫폼입니다.

웹과 API는 하나의 모노레포에서 계약과 변경 이력을 공유하지만, 각각 독립된
프로세스로 실행하고 배포할 수 있습니다.

MVP는 조회 전용입니다. 수집 실행·재실행·삭제 API나 버튼은 없고, 화면 데이터는
운영자가 `새로고침`을 눌렀을 때만 다시 조회합니다. 로그인은 향후 OIDC/사내
SSO/JWT를 연결할 수 있는 역할 경계만 있으며 현재 구현되어 있지 않습니다.

## 구조

```text
apps/
├─ web/                 # React 19 + TypeScript + Vite 웹 애플리케이션
└─ api/                 # Python 3.12 + FastAPI API 애플리케이션
docs/
├─ 설계/
├─ 구현계획/
└─ 운영/
```

## 개발 명령

먼저 Node.js 22.13.0 이상과 Python 3.12를 준비합니다. API 가상환경은
`apps/api/.venv`에 생성하며, 사용 중인 운영체제에 맞는 활성화 명령을 실행한
상태에서 API 테스트를 실행합니다.

```powershell
# 웹 의존성 설치
npm install

# API 및 테스트 의존성 설치
py -3.12 -m venv apps/api/.venv
apps/api/.venv/Scripts/python.exe -m pip install -e "apps/api[test]"
apps/api/.venv/Scripts/Activate.ps1
```

macOS 또는 Linux에서는 다음 명령을 사용합니다.

```bash
python3.12 -m venv apps/api/.venv
apps/api/.venv/bin/python -m pip install -e "apps/api[test]"
source apps/api/.venv/bin/activate
```

루트에서 공통 명령을 실행할 수 있습니다.

```powershell
# 웹 테스트
npm test

# API 테스트
npm run test:api

# 웹 정적 검사 및 타입 검사
npm run lint
npm run typecheck

# 웹 프로덕션 빌드
npm run build
```

API와 웹의 실제 로컬 실행, 환경변수 위치, 읽기 전용 DB 계정 준비 방법은
[`docs/운영/로컬-실행.md`](docs/운영/로컬-실행.md)를 따릅니다. 배포,
reverse proxy, 여덟 상태별 조치와 장애 대응은
[`docs/운영/배포-및-장애대응.md`](docs/운영/배포-및-장애대응.md)에 있습니다.

세 DB 연결 환경변수 중 설정된 소스만 API에 등록됩니다. 모두 없으면
`/health/live`는 프로세스 생존을 나타내므로 200이지만 `/health/ready`는
명확히 503을 반환합니다. 연결 문자열은 데이터 소스별 SELECT 전용 계정과
`ApplicationIntent=ReadOnly`를 사용해야 하며, 앱 시작 시 DB 연결이나 수집
작업을 실행하지 않습니다.

SmartPlace는 naverDB의 `SMARTPLACE_COLLECTION_RUN`과
`SMARTPLACE_COLLECTION_ATTEMPT`를 SELECT 전용 계정으로 조회합니다. 한촌설렁탕과
육수당은 실행 이력의 별도 브랜드 행으로 표시되고 상세에서 `login`, `normal`,
`pos_linked` 시도를 확인할 수 있습니다. DBA 적용, 크롤러 계측 배포, 첫 예약 회차
대조와 롤백은
[`docs/운영/smartplace-사후-모니터링.md`](docs/운영/smartplace-사후-모니터링.md)를
따릅니다.

## MVP 원칙

- 읽기 전용 모니터링
- FC다움, HMR 및 SmartPlace 지원
- 수집기 어댑터 기반 확장
- 로그인 구현은 유보하되 인증·권한 경계는 포함
- `PARTIAL_FAILED`는 화면에서 `부분 실패`로 표시하는 장애 상태

## 네이버 영업시간

`naver-store-hours`는 정규 예약 실행을 브랜드별로 기록하는 독립 수집기다.
크롤러의 전용 감사 기록을 SELECT 전용 계정으로 조회하며 검토/실패 매장,
dry-run 예상과 Apply 확정 매장, 대상 커버리지 및 성공 확인 시각을 구분한다.
실제 예약 설정 확인 전 주간 누락/중단 판정은 비활성화한다.
설정·DBA 검토·첫 정규 회차 검증·롤백은
[네이버 영업시간 운영 문서](docs/운영/naver-store-hours-사후-모니터링.md)를 참고한다.