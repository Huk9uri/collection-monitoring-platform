# SmartPlace 사후 수집 모니터링 설계

## 1. 배경과 목표

SmartPlace 사전검사는 네이버 계정 보호조치처럼 시스템이 통제할 수 없는 인증
상태 때문에 실제 수집 전에 차단될 수 있다. 이 경우 사전검사의 연속 운영 성공을
확인하기 어렵고, 로그인·파싱·적재 실패를 운영자가 여러 서버와 로그에서 직접
확인해야 한다.

이 설계의 목표는 기존 SmartPlace 수집을 대시보드에서 제어하지 않으면서, 실제
수집 실행과 브랜드별·하위 작업별 결과를 `collection-monitoring-platform`에서
읽기 전용으로 한눈에 확인하는 것이다. 이메일 장애 리포트는 이 조회 계약이
안정화된 뒤 수행하는 다음 MVP로 분리한다.

## 2. 범위와 비범위

### 2.1 이번 MVP 범위

- SmartPlace 수집기가 사용하는 naverDB에 실행 요약과 하위 작업 시도를 기록한다.
- SmartPlace의 한촌설렁탕과 육수당을 실행 이력의 별도 행으로 표현한다.
- 각 브랜드 실행 상세에서 `login`, `normal`, `pos_linked` 하위 작업을 확인한다.
- Monitoring API에 SmartPlace 읽기 전용 어댑터를 추가한다.
- 공통 실행 모델에 범위 식별자인 `scope_id`, `scope_name`을 추가한다.
- 대시보드 실행 이력에 브랜드를 표시하고 기존 실행 상세 UI를 재사용한다.
- 로그인·계정 보호조치·브라우저·페이지·파싱·DB·프로세스 오류를 구분한다.
- 예정 실행 누락과 장시간 `RUNNING` 상태를 조회 시점에 판정한다.

### 2.2 비범위

- 대시보드에서 크롤러 실행·중지·재실행
- Windows 작업 스케줄러 조작
- 크롤러 설정, 계정 또는 비밀번호 변경
- 대시보드에서 운영 DB 실행 이력이나 업무 데이터 수정
- 크롤러 서버의 로그 파일 또는 브라우저 프로필 직접 접근
- HTML 원문, 쿠키, 자격 증명 또는 원문 traceback 저장·노출
- 이번 MVP에서 이메일 발송
- HMR 및 FC다움 수집기 스키마 변경

## 3. 핵심 원칙

1. 크롤러는 자신의 실행 결과만 기록하고 독립된 기존 일정으로 실행한다.
2. Monitoring API는 수집기별 DB를 읽기 전용 계정으로 조회한다.
3. 웹 앱은 SmartPlace와 naverDB의 물리 스키마를 알지 않는다.
4. 모니터링 기록 실패가 실제 수집 성공 여부를 바꾸지 않는다.
5. 알 수 없는 값은 정상적인 `0`으로 위장하지 않고 `NULL`로 보존한다.
6. 원시 오류는 표준 오류 코드와 비밀정보를 제거한 짧은 요약으로 변환한다.
7. HMR과 FC다움의 기존 API·화면·상태 판정을 회귀시키지 않는다.

## 4. 아키텍처

```text
Windows 작업 스케줄러
  -> SmartPlace 크롤러
       -> 기존 업무 데이터 적재
       -> naverDB SmartPlace 실행 이력 기록
                          |
                          | SELECT 전용
                          v
                 Monitoring API
                   SmartPlace Adapter
                          |
                          v
                  공통 모니터링 모델
                          |
                          v
                       Web UI
```

HMR은 ecommerce DB, FC다움과 SmartPlace는 naverDB를 조회한다. 물리 DB는 달라도
Monitoring API가 모두 `CollectorRun`과 `CollectorAttempt`로 정규화한다.

## 5. 공통 모델 확장

`CollectorRun`에 다음 필드를 추가한다.

- `scope_id: str | None`: 수집기 내부 실행 범위의 안정 식별자
- `scope_name: str | None`: 사용자에게 표시할 범위 이름

SmartPlace는 `collector_id=smartplace`를 유지하고 다음처럼 매핑한다.

| collector_id | scope_id | scope_name |
|---|---|---|
| `smartplace` | `hanchon` | `한촌설렁탕` |
| `smartplace` | `yuksoodang` | `육수당` |

HMR과 FC다움은 두 필드를 `NULL`로 반환해 기존 의미를 유지한다. 브랜드를 별도
수집기 ID로 만들지 않으므로 SmartPlace의 일정·신선도·준비 상태를 중복 등록하지
않는다.

## 6. naverDB 기록 계약

### 6.1 `SMARTPLACE_COLLECTION_RUN`

브랜드별 실행 하나를 나타낸다.

| 컬럼 | 의미 |
|---|---|
| `RunId uniqueidentifier` | 브랜드 실행 ID |
| `ScheduledAt datetime2(0)` | 예정 실행 시각 |
| `BrandCode varchar(50)` | 안정 브랜드 코드 |
| `BrandName nvarchar(100)` | 표시 브랜드명 |
| `StartedAt datetime2(3)` | 시작 시각 |
| `FinishedAt datetime2(3) NULL` | 완료 시각 |
| `RunStatus varchar(30)` | 원시 실행 상태 |
| `SuccessfulUnits int` | 성공한 최종 하위 작업 수 |
| `FailedUnits int` | 실패한 최종 하위 작업 수 |
| `ErrorCategory varchar(50) NULL` | 실행 전체 오류 분류 |
| `ErrorSummary nvarchar(500) NULL` | 정제된 오류 요약 |
| `CorrelationId varchar(100) NULL` | 서버 로컬 로그 상관 ID |
| `HostName nvarchar(128) NULL` | 실행 호스트 |
| `ApplicationVersion varchar(64) NULL` | 배포 버전 |

기본키는 `RunId`, 고유키는 `(ScheduledAt, BrandCode)`로 한다. 시간은 DB에 UTC로
저장하고 API에서도 UTC-aware ISO 8601로 반환한다.

### 6.2 `SMARTPLACE_COLLECTION_ATTEMPT`

브랜드 실행의 단계별 시도를 나타낸다.

| 컬럼 | 의미 |
|---|---|
| `RunId uniqueidentifier` | 상위 브랜드 실행 ID |
| `UnitCode varchar(50)` | `login`, `normal`, `pos_linked` |
| `UnitName nvarchar(100)` | 화면 표시명 |
| `AttemptNo int` | 같은 작업의 시도 번호 |
| `StartedAt datetime2(3)` | 시도 시작 시각 |
| `FinishedAt datetime2(3) NULL` | 시도 완료 시각 |
| `AttemptStatus varchar(30)` | 원시 시도 상태 |
| `SourceCount int NULL` | 원천 대상 수 |
| `InsertedCount int NULL` | 신규 적재 수 |
| `ChangedCount int NULL` | 변경 적재 수 |
| `UnchangedCount int NULL` | 동일 수 |
| `DbCommitted bit NULL` | 업무 데이터 commit 여부 |
| `ErrorCategory varchar(50) NULL` | 표준 오류 분류 |
| `ErrorSummary nvarchar(500) NULL` | 정제된 오류 요약 |
| `CorrelationId varchar(100) NULL` | 서버 로컬 로그 상관 ID |

기본키는 `(RunId, UnitCode, AttemptNo)`이며 `RunId`는 실행 테이블을 참조한다.
실패 전에 집계할 수 없었던 건수는 `NULL`이고 UI에는 `-`로 표시한다.

## 7. 기록 흐름과 장애 격리

1. 크롤러 프로세스가 시작되면 예정 브랜드별 `RUNNING` 실행 행을 먼저 기록하고
   독립 commit한다.
2. 각 브랜드에서 `login`, `normal`, `pos_linked` 시도를 시작·종료할 때 시도 행을
   기록한다.
3. 하위 작업의 업무 데이터 commit 여부와 집계값은 확인된 값만 기록한다.
4. 브랜드 처리가 끝나면 하위 작업 최종 시도를 기준으로 실행 상태와 완료 시각을
   갱신한다.
5. 재시도는 기존 시도를 덮어쓰지 않고 `AttemptNo`를 증가시킨다.
6. 모니터링 INSERT/UPDATE가 실패하면 정제된 로컬 로그를 남기고 기존 수집 흐름은
   계속한다. 업무 데이터 트랜잭션과 모니터링 트랜잭션은 공유하지 않는다.
7. 최상위 예외 처리에서 가능한 실행·시도를 실패로 종료한다. 강제 종료처럼 이
   처리가 불가능한 경우 Monitoring API의 stale 판정이 보완한다.

동일한 `(ScheduledAt, BrandCode)`가 다시 실행되면 새 실행 행을 만들지 않고 같은
`RunId` 아래에 새 시도를 추가한다. 이미 성공한 작업을 실제로 다시 수행하지
않았다면 성공 시도를 복제하지 않는다.

## 8. 상태와 오류 분류

### 8.1 원시 상태

- `RUNNING`
- `SUCCESS`
- `SUCCESS_EMPTY`
- `WARNING`
- `PARTIAL_FAILED`
- `FAILED`
- `ABORTED`
- `NOT_RUN`

최종 시도 중 모두 성공하면 `SUCCESS`, 일부만 성공하면 `PARTIAL_FAILED`, 성공한
시도가 없으면 `FAILED`다. 실패 후 재시도로 모두 성공하면 `WARNING`이다.

### 8.2 표준 오류 코드

- `ACCOUNT_PROTECTED`
- `LOGIN_FAILED`
- `BROWSER_FAILED`
- `PAGE_LOAD_FAILED`
- `PARSE_FAILED`
- `DB_FAILED`
- `PROCESS_CRASHED`
- `TIMEOUT`
- `PREREQUISITE_FAILED`
- `UNKNOWN`

예외 클래스만으로 계정 보호조치를 추측하지 않는다. 실제로 확인된 보호조치 화면
신호가 있을 때만 `ACCOUNT_PROTECTED`를 사용하며, 그렇지 않은 인증 실패는
`LOGIN_FAILED`로 기록한다. 상세 예외, 쿼리, 계정명, URL query, HTML은 공개
요약에 포함하지 않는다.

## 9. 미실행과 중단 실행 판정

SmartPlace 정책에는 시간대, 일일 예정 시각, 시작 유예시간, 최대 실행시간과 예상
브랜드 목록을 설정한다. 이 값은 코드에 고정하지 않는다.

- 예정 시각 전 실행 행 없음: 이상 없음
- 예정 시각과 시작 유예시간이 지난 뒤 브랜드 행 없음: 조회 결과 `NOT_RUN`
- `RUNNING`이 최대 실행시간을 초과: 조회 결과 `ABORTED`
- 한 브랜드만 기록된 경우: 기록되지 않은 브랜드만 `NOT_RUN`

이 판정은 Monitoring API가 조회 시점에 계산하며 원본 DB 행을 수정하지 않는다.
프로세스가 한촌 처리 후 육수당 시작 전에 종료되면 한촌은 실제 상태를, 육수당은
`NOT_RUN`을 표시한다.

## 10. Monitoring API와 UI

SmartPlace 어댑터는 naverDB의 두 테이블을 고정 SQL과 파라미터 바인딩으로 조회해
기존 목록·개수·상태별 개수·최신·상세·준비 상태 계약을 구현한다. 한 DB 장애가
HMR 등 다른 어댑터의 정상 결과를 가리지 않는 기존 bulkhead를 유지한다.

실행 이력은 SmartPlace 브랜드별 한 행을 표시한다. 기존 열에 브랜드 열을 추가하고
SmartPlace 행에서는 `scope_name`을 표시한다. 행을 선택하면 기존 실행 상세 패널에
`login`, `normal`, `pos_linked` 시도와 상태, 집계, 오류 분류를 표시한다. `NULL`
집계는 `-`로 표시한다.

SmartPlace 요약 카드는 최신 예정 회차의 두 브랜드 중 가장 심각한 상태를 사용한다.
전체 장애 실행 수는 실패한 브랜드 행 수를 집계해 부분 장애를 숨기지 않는다.

## 11. 권한과 보안

- SmartPlace 크롤러 계정에는 두 실행 이력 테이블의 필요한 `SELECT`, `INSERT`,
  `UPDATE`만 부여한다.
- Monitoring API 계정에는 두 테이블과 승인된 업무 신선도 조회 대상의 `SELECT`만
  부여한다.
- DDL 권한, 실행 권한, 작업 스케줄러 권한을 Monitoring API에 부여하지 않는다.
- API 응답에는 `ErrorSummary`를 그대로 노출하지 않고 허용된 길이와 패턴으로 한 번
  더 정제한다.
- 비밀번호, 쿠키, 토큰, HTML 원문과 traceback은 DB 및 API 계약 밖에 둔다.

## 12. 테스트 전략

### 12.1 SmartPlace 크롤러

- 실행 시작, 단계 성공·실패, 브랜드 최종 상태 기록
- 한촌 성공 후 육수당 보호조치 실패
- NORMAL 성공 후 POS 파싱 실패
- 중복 실행의 시도 번호 증가와 기존 성공 증거 보존
- 모니터링 DB 기록 실패가 업무 수집 결과를 변경하지 않음
- 오류 요약의 비밀정보 제거

### 12.2 Monitoring API

- SmartPlace SQL 별칭과 공통 모델 매핑
- 브랜드별 실행 행과 단계별 시도 반환
- `NULL` 집계 보존
- 상태 필터·페이지네이션·상태별 개수
- 누락 브랜드 `NOT_RUN` 합성
- stale `RUNNING`의 `ABORTED` 판정
- naverDB 장애 시 HMR 결과 유지
- HMR·FC다움 전체 회귀

### 12.3 Web

- 브랜드 열 표시
- 브랜드별 행 구분
- 실행 상세의 `login`, `normal`, `pos_linked` 표시
- 알 수 없는 집계를 `-`로 표시
- 오류 분류 표시와 원문 오류 비노출
- 실행·재실행·중지 UI가 존재하지 않음

## 13. 배포 순서와 롤백

1. DBA 검토 후 naverDB 테이블과 최소 권한을 적용한다.
2. Monitoring API SmartPlace 어댑터를 연결하되 준비 상태 실패가 다른 수집기를
   가리지 않는지 확인한다.
3. Web의 브랜드 행과 상세 표시를 배포한다.
4. SmartPlace 크롤러 계측을 배포한다.
5. 첫 예약 실행에서 브랜드별 run, 세 단계 attempt, 업무 적재 결과를 대조한다.

롤백 시에는 SmartPlace 크롤러 계측과 Monitoring API의 SmartPlace 등록만 이전
릴리스로 되돌린다. 생성된 감사 테이블과 과거 행은 삭제하지 않는다. HMR·FC다움
어댑터와 기존 수집 일정은 변경하지 않는다.

## 14. 다음 MVP: 장애 이메일 리포트

다음 MVP는 플랫폼이 읽기 전용 조회 결과에서 새 `FAILED`, `PARTIAL_FAILED`,
`ABORTED`, `NOT_RUN`을 감지해 이메일을 발송한다. 중복 발송 방지와 재시도 상태는
크롤러 DB가 아닌 플랫폼 소유 저장소에 기록한다. 이메일 실패는 수집기 상태를
변경하지 않으며, 메일에는 브랜드, 예정 시각, 실패 단계, 표준 오류 코드와 정제된
요약만 포함한다.

## 15. 완료 조건

- 한촌설렁탕과 육수당이 SmartPlace 실행 이력의 별도 행으로 표시된다.
- 상세에서 `login`, `normal`, `pos_linked`의 최종 및 과거 시도를 확인할 수 있다.
- 계정 보호조치, 일반 로그인 실패, 파싱 실패와 DB 실패가 구분된다.
- 예정 실행 누락과 중단 실행이 자동 판정된다.
- 대시보드와 API에 크롤러 제어 또는 운영 DB 변경 기능이 없다.
- 비밀정보와 원문 운영 로그가 DB·API·화면에 노출되지 않는다.
- HMR과 FC다움의 기존 동작 및 회귀 테스트가 유지된다.
