# Collection Monitoring Platform

FC다움, HMR 및 향후 추가될 데이터 수집기의 실행·적재·신선도를 한곳에서
확인하기 위한 사내 운영 모니터링 플랫폼입니다.

웹과 API는 하나의 모노레포에서 계약과 변경 이력을 공유하지만, 각각 독립된
프로세스로 실행하고 배포할 수 있습니다.

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

웹 개발 서버는 `npm run dev --workspace=@collection-monitoring/web`로
실행합니다. 웹은 `.env`의 `VITE_MONITORING_API_URL`로 읽기 전용 API 주소를
설정하며, 필요한 키는 `.env.example`을 참고합니다.

## MVP 원칙

- 읽기 전용 모니터링
- FC다움 및 HMR 우선 지원
- 수집기 어댑터 기반 확장
- 로그인 구현은 유보하되 인증·권한 경계는 포함
- `PARTIAL_FAILED`는 화면에서 `부분 실패`로 표시하는 장애 상태
