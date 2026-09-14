# 로그인 및 모니터링 기준 일정 관리 Handoff

## 1. 현재 상태

2026-09-14 후속 작업에서 로그인·세션, DB 정책 저장·감사, 주간·복수 회차 판정,
웹 로그인·viewer 조회·admin 편집과 충돌 복구, 계정 생성·초기화 CLI를 구현했다.
사용자가 DDL을 적용했고 초기 관리자 생성 및 실제 DB 로그인·로그아웃 smoke도
완료했다. 세부 운영 절차는 `docs/운영/로그인-및-기준-일정.md`를 참조한다.

작업 브랜치는 `codex/monitoring-control-schema`다. 기존 수집기 미커밋 변경과 함께
작업 트리에 남아 있으며 커밋하지 않았다. 아래 구현 순서는 원래의 설계 기준이다.

현재 남은 배포 확인: HTTPS 웹/API 주소와 프록시 설정, 최소 권한 제어 계정 교체,
실제 수집 일정에 맞는 최초 정책 저장. 사용자는 별도 로그인 운영 정책 설정을
두지 않도록 요청했으며 추가 로그인 환경변수는 요구하지 않는다.

설계 문서:

- `docs/설계/2026-09-14-로그인-및-모니터링-기준-일정-관리.md`

작업 저장소:

- `C:\workspace\collection-monitoring-platform`

현재 `main` 작업 트리에는 스마트플레이스와 네이버 영업시간 모니터링 관련
미커밋 변경이 존재한다. 해당 변경은 이 기능의 일부가 아니며 덮어쓰기, 삭제,
stash, reset 또는 함께 커밋하면 안 된다. 구현을 시작할 때는 최신 변경의 소유자와
병합 상태를 먼저 확인하고 별도 `codex/` 브랜치 또는 격리 worktree를 사용한다.

## 2. 확정된 요구사항

- 인터넷에서 접근 가능한 대시보드이므로 비로그인 사용자는 모니터링 데이터를 볼
  수 없다.
- `viewer`는 모니터링 현황과 모니터링 기준 일정을 조회할 수 있다.
- `admin`은 viewer 권한에 더해 모니터링 기준 일정을 수정하고 변경 이력을
  조회할 수 있다.
- 실제 Windows 작업 스케줄러와 수집기 실행 일정은 변경하지 않는다.
- 화면에서 변경하는 값은 대시보드의 `NOT_RUN`, `ABORTED`, `WARNING` 등
  상태 판정 기준이다.
- DB 정책이 우선이며 기존 `.env` 정책은 초기값과 장애 fallback으로 유지한다.
- 설정 저장은 변경자, 변경 사유, 변경 전후 값을 감사 이력에 남긴다.
- 설계·구현·운영 문서는 한국어로 작성한다.

## 3. 기존 코드에서 확인한 지점

### API

- `apps/api/src/monitoring_api/auth.py`
  - 현재 `get_current_user()`가 모든 요청에 익명 `viewer`를 반환한다.
  - 이를 세션 쿠키 기반 인증으로 교체해야 한다.
- `apps/api/src/monitoring_api/models.py`
  - 기존 역할은 `viewer`, `operator`, `admin`이다.
  - 이번 기능은 `viewer`와 `admin`을 사용한다.
  - `operator`의 의미는 변경하지 않는다.
- `apps/api/src/monitoring_api/api/monitoring.py`
  - 모든 모니터링 경로에 이미 `Role.VIEWER` dependency가 있다.
  - 인증 공급자 교체 후 이 경계를 그대로 활용한다.
- `apps/api/src/monitoring_api/config.py`
  - 수집기별 timezone, 예정 시각, 실행시간, 신선도 SLA가 `.env` 설정으로
    정의돼 있다.
- `apps/api/src/monitoring_api/composition.py`
  - 현재 환경 설정을 어댑터 정책으로 조립한다.
  - DB 정책 repository와 fallback 조합 지점을 추가해야 한다.
- `apps/api/src/monitoring_api/services/monitoring.py`
  - 일일 예정 시각을 기준으로 미실행과 장기 실행을 판정한다.
  - 다중 요일·다중 시각 일정 계산을 별도 정책 서비스로 분리하는 것이 좋다.
- `apps/api/tests/test_auth.py`
  - 익명 사용자가 viewer라는 기존 테스트를 로그인 필수 계약으로 교체해야 한다.

### 웹

- 현재 모니터링 화면에는 로그인, 세션 복구, 역할별 라우트 경계가 없다.
- 기존 모니터링 API 호출부가 `401`을 공통 처리하고 로그인 경로로 이동하도록
  요청 계층을 확장해야 한다.
- 기존 디자인 시스템과 공통 레이아웃을 우선 재사용한다.

## 4. 권장 파일 구조

구현 전 실제 저장소 구조와 현재 변경을 다시 확인한다. 다음은 책임 분리를 위한
권장안이다.

```text
apps/api/
├─ sql/
│  ├─ 100_create_monitoring_control_tables.sql
│  └─ 105_verify_monitoring_control_tables.sql
├─ src/monitoring_api/
│  ├─ api/auth.py
│  ├─ api/settings.py
│  ├─ auth.py
│  ├─ control_db.py
│  ├─ security.py
│  ├─ repositories/auth.py
│  ├─ repositories/policy.py
│  └─ services/policy.py
└─ tests/
   ├─ test_auth_api.py
   ├─ test_auth_repository.py
   ├─ test_policy_api.py
   ├─ test_policy_repository.py
   └─ test_policy_service.py

apps/web/src/features/
├─ auth/
│  ├─ components/login-form.tsx
│  ├─ data/api.ts
│  ├─ data/schema.ts
│  └─ login-page.tsx
└─ monitoring-settings/
   ├─ components/schedule-form.tsx
   ├─ data/api.ts
   ├─ data/schema.ts
   └─ schedule-page.tsx
```

기존 구조에서 같은 책임을 가진 파일이 이미 생겼다면 새 파일을 병렬로 만들지 말고
기존 구현을 확장한다.

## 5. DB 변경

설계 문서에 정의된 다음 테이블이 필요하다.

- `monitoring_user`
- `monitoring_session`
- `monitoring_collector_policy`
- `monitoring_collector_schedule`
- `monitoring_collector_freshness_policy`
- `monitoring_policy_history`
- `monitoring_auth_audit`

DDL은 모니터링 앱의 런타임 DB 계정으로 실행하지 않는다. DBA 또는 승인된
마이그레이션 계정으로 100 스크립트를 적용하고, 105 SELECT-only 스크립트로
테이블·컬럼·제약조건·인덱스와 런타임 계정 권한을 검증한다.

기존 수집 데이터 연결은 계속 `ApplicationIntent=ReadOnly`를 유지한다. 인증과
설정에는 별도 `MONITORING_CONTROL_CONNECTION_STRING`을 사용하고 수집 업무
테이블 DML 권한을 부여하지 않는다.

## 6. 구현 순서

모든 기능은 테스트 우선으로 구현한다.

1. SQL 스키마 계약 테스트와 100·105 스크립트 작성
2. 제어 DB 연결과 최소 권한 repository
3. Argon2id 비밀번호, 세션 토큰 해시, CSRF 보안 함수
4. 사용자·세션 repository와 로그인 API
5. 기존 익명 viewer dependency를 로그인 사용자 dependency로 교체
6. 정책·일정·신선도 repository와 감사 트랜잭션
7. DB 정책 → 캐시 → `.env` fallback 정책 서비스
8. 다중 요일·다중 시각 예정 회차 계산
9. 정책 조회·수정·변경 이력 API와 rowversion 충돌 처리
10. 웹 로그인·세션 복구·로그아웃
11. viewer 읽기 전용 일정 화면
12. admin 일정 편집·변경 사유·저장 확인·충돌 복구
13. 한국어 운영 문서와 계정 초기화 CLI
14. 전체 API·웹 테스트, typecheck, lint, build, 실제 SELECT-only smoke

## 7. 보안상 반드시 지킬 사항

- 평문 비밀번호, 세션 토큰, CSRF 토큰을 DB와 로그에 저장하지 않는다.
- 세션 쿠키는 `HttpOnly`, `Secure`, `SameSite=Lax`로 설정한다.
- 쓰기 요청은 세션, 역할, CSRF 토큰, Origin을 모두 검사한다.
- 외부 URL을 `returnTo`로 허용하지 않는다.
- 로그인 실패 응답으로 사용자 존재 여부를 노출하지 않는다.
- 정책 변경과 감사 이력 INSERT를 하나의 트랜잭션으로 처리한다.
- 웹에서 admin 메뉴를 숨기는 것만으로 권한을 통제하지 않는다.
- 운영 환경에서 API 문서와 상세 readiness를 공개하지 않는다.
- HTTPS 없이 운영 로그인을 활성화하지 않는다.

## 8. 화면 문구

설정 화면 명칭은 `스케줄러 설정`이 아니라 `모니터링 기준 일정`을 사용한다.
다음 안내를 항상 노출한다.

> 이 설정은 대시보드의 상태 판정 기준만 변경하며 실제 수집기 실행 일정에는
> 영향을 주지 않습니다.

저장 전에는 실제 수집 일정과 같은 값인지 확인하고 필수 변경 사유를 입력하도록
한다.

## 9. 검증 명령

프로젝트 루트에서 현재 환경에 맞는 실행 파일을 사용한다.

```powershell
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests -p no:cacheprovider
npm test
npm run typecheck
npm run lint
npm run build
```

실제 DB smoke는 승인된 제어 DB 계정과 변경된 비밀번호를 사용한다. 수집기 실행,
Windows 작업 스케줄러 변경, 수집 업무 테이블 DML은 smoke 범위에 포함하지 않는다.

## 10. 아직 결정하거나 확인할 운영값

아래 값은 구현 중 임의로 추측하지 않는다.

- 운영 도메인과 HTTPS 종료 위치
- 로그인 실패 제한 횟수와 잠금 시간의 최종 운영값
- 초기 viewer·admin 계정명
- 사용자 비밀번호 최소 길이와 조직 비밀번호 정책
- 세션 유휴 8시간·절대 24시간 정책의 운영 승인
- 제어 테이블을 둘 SQL Server 데이터베이스와 스키마
- 각 수집기의 실제 요일·시각·유예·귀속 범위·신선도 SLA

## 11. 다음 작업자의 첫 확인 사항

1. `git status --short --branch`로 현재 미커밋 변경을 확인한다.
2. 스마트플레이스·네이버 영업시간 작업과 겹치는 파일의 소유 상태를 확인한다.
3. 설계 문서에 대한 사용자 검토가 완료됐는지 확인한다.
4. 승인 후 한국어 구현 계획을 작성한다.
5. 격리 브랜치 또는 worktree에서 TDD로 구현한다.
