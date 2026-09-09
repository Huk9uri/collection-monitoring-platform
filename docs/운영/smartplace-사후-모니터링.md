# SmartPlace 사후 모니터링 운영

## 1. 목적과 변경 금지 경계

이 기능은 SmartPlace 크롤러가 naverDB에 남긴 실행·적재 결과를 브랜드와 하위
작업 단위로 조회한다. 한촌설렁탕(`hanchon`)과 육수당(`yuksoodang`)은 실행
이력에서 별도 행이고, 상세에는 `login`, `normal`, `pos_linked` 시도가 표시된다.

대시보드에서 실행하지 않는다. 대시보드와 Monitoring API는 다음 동작을 하지
않는다.

- SmartPlace 크롤러 실행·중지·재실행
- Windows 작업 스케줄러 조회·수정·트리거
- 계정 보호조치 해제, 자격 증명이나 브라우저 프로필 변경
- 운영 DB의 INSERT, UPDATE, DELETE, MERGE, DDL
- 서버 로그·HTML·쿠키·비밀번호 수집
- 이메일 발송

Monitoring API는 별도 SELECT 전용 계정으로만 naverDB에 접속한다. 크롤러의
모니터링 기록 실패도 업무 데이터 수집 결과를 바꾸지 않도록 격리되어 있다.

## 2. 적용 전 승인 게이트

아래 항목은 서로 독립된 승인 게이트다. 구현 코드가 준비되어 있어도 승인 없이
운영 DB, 서버, 예약 작업 또는 메일에 적용하지 않는다.

1. naverDB 감사 DDL 적용과 백업 정책
2. 크롤러 계정과 Monitoring API 계정의 최소 권한
3. SmartPlace 크롤러 계측 배포
4. Monitoring API·웹 배포와 환경변수 주입
5. 실제 첫 예약 회차 관찰
6. 후속 MVP인 이메일 구현·발송

## 3. DDL 사전검토와 적용 순서

SQL 파일은 `C:\workspace\naver_crawling\scripts\sql\smartplace_monitoring`에 있다.

1. DBA가 `01_create.sql`을 읽고 대상 DB가 naverDB인지 검사하는 방어문, 트랜잭션,
   컬럼, 제약조건을 검토한다.
2. 변경 승인과 DB 백업·복구 정책을 확인한다.
3. DBA 또는 승인된 마이그레이션 계정으로 naverDB를 명시한 세션에서
   `01_create.sql`을 적용한다. 이 스크립트는
   `SMARTPLACE_COLLECTION_RUN`과 `SMARTPLACE_COLLECTION_ATTEMPT`만 생성한다.
4. `02_verify.sql`을 실행해 두 테이블의 컬럼, 기본키, `(ScheduledAt, BrandCode)`
   고유키, attempt 외래키와 CHECK 제약조건을 확인한다. `02_verify.sql`은 시스템
   카탈로그를 읽는 SELECT-only 검증이다.
5. 결과가 설계와 다르면 이후 배포를 중단하고 DBA가 원인을 조사한다. 장애 대응
   중 `01_create.sql`을 임의 재실행하지 않는다.

DDL 적용 중에는 크롤러나 Windows 예약 작업을 수동 실행하지 않는다.

## 4. 최소 권한 분리

| 주체 | 허용 권한 | 금지 권한 |
| --- | --- | --- |
| SmartPlace 크롤러 계정 | 두 감사 테이블의 필요한 `SELECT`, `INSERT`, `UPDATE` | DDL, 감사 행 삭제, 대시보드 관리 |
| Monitoring API 계정 | 두 감사 테이블 및 별도 승인된 신선도 대상의 `SELECT` | `INSERT`, `UPDATE`, `DELETE`, `MERGE`, DDL, 실행 권한 |
| DBA/마이그레이션 계정 | 승인 시간의 `01_create.sql` 적용 | 상시 API 연결 문자열 사용 |

API 연결 문자열에는 `ApplicationIntent=ReadOnly`를 넣고 비밀 저장소에서 주입한다.
이 옵션은 보조 방어이므로 DB의 SELECT 전용 권한을 대신하지 않는다. API 계정으로
`02_verify.sql`을 다시 실행해 실제 조회 권한과 DML/DDL 부재를 검증한다.

## 5. 배포 전 비운영 검증

두 저장소의 격리된 개발 환경에서 다음 회귀를 실행한다. 이 명령들은 운영 DB,
브라우저, 예약 작업, 이메일을 호출하지 않아야 한다.

```powershell
# naver_crawling
python -m pytest `
  tests/test_smartplace_monitoring_sql.py `
  tests/test_smartplace_monitoring.py `
  tests/test_smartplace_crawler_v22.py `
  tests/test_smartplace_browser.py `
  tests/test_smartplace_parsers.py -q

# collection-monitoring-platform
python -m pytest apps/api/tests -q
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

테스트 fixture와 mock 결과는 운영 smoke로 기록하지 않는다. 한 명령이라도 실패하면
배포를 중단하고 실제 실패와 로컬 환경 제약을 구분해 기록한다.

## 6. 운영 배포 순서

1. 3절에 따라 DDL을 적용하고 `02_verify.sql`을 통과시킨다.
2. 크롤러 계정에 두 감사 테이블의 최소 기록 권한을 부여한다. 아직 크롤러를
   실행하지 않는다.
3. SmartPlace 계측이 포함된 크롤러 artifact를 배포한다. 기존 예약 시각, 계정
   범위, 브라우저 설정과 업무 적재 설정은 바꾸지 않는다.
4. Monitoring API 계정에 SELECT 권한만 부여하고 다음 값을 비밀 저장소·배포
   환경에 주입한다.
   - `MONITORING_SMARTPLACE_CONNECTION_STRING`
   - `MONITORING_SMARTPLACE_SCHEDULE_TIMEZONE`
   - `MONITORING_SMARTPLACE_DAILY_SCHEDULED_TIME`
   - `MONITORING_SMARTPLACE_START_GRACE_MINUTES`
   - `MONITORING_SMARTPLACE_MAX_DURATION_MINUTES`
   - `MONITORING_SMARTPLACE_SCHEDULE_ATTRIBUTION_WINDOW_MINUTES`
   - `MONITORING_SMARTPLACE_EXPECTED_SCOPES`
5. Monitoring API를 배포하고 `/health/live`, `/health/ready`, collectors, runs 순서로
   SELECT-only smoke를 수행한다. SmartPlace 실패가 HMR·FC다움 결과를 가리지
   않는지도 확인한다.
6. 웹을 배포하고 한촌설렁탕·육수당 브랜드 열과 실행 상세 레이아웃을 확인한다.
7. 승인된 다음 정규 예약 회차를 기다린다. 대시보드에서 크롤러를 트리거하지
   않는다.

## 7. 첫 예약 실행 대조

실제 예약 시각, 시작 유예시간과 귀속 창은 Windows 예약 작업의 승인된 설정과
일치해야 한다. 첫 정규 회차 뒤 화면에서 수동 `새로고침`하고 다음을 대조한다.

| 점검 대상 | 기대 결과 |
| --- | --- |
| 브랜드 행 | 같은 예정 회차에 한촌설렁탕과 육수당이 각각 한 행 |
| 로그인 | 각 브랜드 상세에 `login` 시도와 최종 상태 |
| 화면 작업 | 확인된 작업에 `normal`, `pos_linked` 시도와 최종 상태 |
| 집계 | 확인할 수 없는 건수는 `0`이 아니라 `-` |
| 적재 | `DbCommitted`와 업무 테이블의 실제 적재 시각·건수를 별도 SELECT로 대조 |
| 오류 | 공개 상세에는 표준 오류 코드와 정제된 요약만 존재 |

화면 종류를 확인할 수 있는 명시적 metadata가 없으면 계정 종류나 브랜드로
Normal/POS를 추측하지 않고 `unknown`으로 기록한다. 따라서 첫 회차에 세 작업이
모두 보이지 않으면 즉시 거짓 성공으로 보정하지 말고 크롤러 job metadata와 해당
실행의 수집 범위를 조사한다.

확인된 계정 보호조치 화면은 로그인 시도에 `ACCOUNT_PROTECTED`로 표시된다. 일반
인증 실패는 `LOGIN_FAILED`, 로그인 때문에 실행하지 못한 후속 작업은
`PREREQUISITE_FAILED`로 구분한다. 한 브랜드가 실패해도 다른 브랜드 결과는
독립적으로 확인한다.

## 8. 누락·중단 판정과 장애 대응

- 예정 시각과 시작 유예시간 뒤 브랜드 행이 없으면 API가 `NOT_RUN`을 합성한다.
- `RUNNING` 행이 최대 실행시간을 넘으면 API가 `ABORTED`로 표시한다.
- 두 판정은 읽기 시점의 결과이며 naverDB 원본을 변경하지 않는다.
- 모니터링 기록 실패는 실제 수집을 중단하지 않으므로 대시보드 이력 누락과 업무
  적재 성공이 동시에 발생할 수 있다. 이 경우 서버의 기존 크롤러 로그와 업무
  테이블의 적재 시각을 수동으로 대조한다.
- 강제 종료로 종료 기록이 남지 않으면 stale `ABORTED` 판정을 사용하고, 재실행
  여부는 대시보드 밖의 승인된 크롤러 운영 절차에서 결정한다.

대시보드에서 실행하지 않는다. 운영자는 상태를 확인하고 원인을 분류할 뿐,
대시보드에서 재시도나 계정 조치를 수행하지 않는다.

## 9. 롤백

DDL 적용 이후 크롤러 또는 플랫폼 문제가 발견되면 다음 범위만 되돌린다.

1. SmartPlace 크롤러를 계측 이전 artifact로 롤백한다. 기존 업무 데이터와 예약
   작업 설정은 변경하지 않는다.
2. Monitoring API에서 SmartPlace 어댑터 등록을 제거하거나 직전 API artifact로
   롤백하고 `MONITORING_SMARTPLACE_*` 주입을 제거한다.
3. 필요하면 웹을 직전 artifact로 롤백한다. HMR·FC다움은 계속 제공한다.
4. live/readiness와 기존 HMR·FC다움 조회를 SELECT-only smoke로 확인한다.

`SMARTPLACE_COLLECTION_RUN`, `SMARTPLACE_COLLECTION_ATTEMPT`와 과거 행은 감사
증거이므로 삭제하지 않는다. DROP, DELETE, TRUNCATE 또는 임의 데이터 보정은 롤백
절차가 아니다. 크롤러 계정의 감사 테이블 쓰기 권한 회수는 계측 롤백과 잔여
프로세스 종료가 확인된 뒤 별도 승인으로 수행한다.

## 10. 알려진 위험과 다음 단계

- 네이버 계정 보호조치는 크롤러가 통제할 수 없다. 해제 전에는 해당 브랜드의
  `ACCOUNT_PROTECTED`와 후속 `PREREQUISITE_FAILED`가 반복될 수 있다.
- 프로세스가 실행 행을 남기기 전에 종료되거나 모니터링 기록이 실패하면 실제
  수집과 대시보드 `NOT_RUN`이 불일치할 수 있다.
- 명시적 화면 metadata가 없는 계정은 `unknown`으로 기록되어 Normal/POS 가시성이
  제한될 수 있다. 이는 잘못된 분류를 피하기 위한 의도된 보수 동작이다.
- 일정·유예·최대 실행시간·귀속 창이 실제 예약 작업과 다르면 `NOT_RUN` 또는
  회차 귀속이 잘못될 수 있다. 배포 전에 값을 추측하지 않고 운영 설정과 대조한다.
- 이메일 장애 리포트는 다음 MVP다. 현재 구현은 이메일을 발송하지 않으며 메일
  실패·중복 방지 상태도 저장하지 않는다.
