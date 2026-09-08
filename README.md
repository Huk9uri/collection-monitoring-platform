# Collection Monitoring Platform

FC다움, HMR 및 향후 추가될 데이터 수집기의 실행·적재·신선도를 한곳에서
확인하기 위한 사내 운영 모니터링 플랫폼입니다.

현재 단계는 설계 승인 단계입니다. 구현은 승인된 설계와 별도 한국어 구현
계획에 따라 진행합니다.

## 예정 구조

```text
apps/
├─ web/  # React + TypeScript + Vite
└─ api/  # FastAPI
docs/
├─ 설계/
├─ 구현계획/
└─ 운영/
```

## MVP 원칙

- 읽기 전용 모니터링
- FC다움 및 HMR 우선 지원
- 수집기 어댑터 기반 확장
- 로그인 구현은 유보하되 인증·권한 경계는 포함
- `PARTIAL_FAILED`는 화면에서 `부분 실패`로 표시하는 장애 상태
