# 네이버 영업시간 모니터링 운영

## 목적과 구조

`naver-store-hours`는 SmartPlace와 독립된 조회 전용 수집기다. 한촌설렁탕(`001` → `hanchon`)과 육수당(`002` → `yuksoodang`)을 각각 실행 이력 행으로 제공한다. 화면은 수동 새로고침하며 실행·중지·재실행·Apply API나 버튼은 없다.

크롤러 예약 진입점 → 검증된 메모리 snapshot → 독립 감사 트랜잭션 → `dbo.NAVER_STORE_HOURS_MONITORING_RUN` → 플랫폼 SELECT 전용 어댑터 → 공통 화면 순서다. 파일 어댑터를 사용하지 않으므로 플랫폼이 크롤러 서버 파일 공유 권한을 가질 필요가 없고 개발 PC 로그에 의존하지 않는다. 서버 절대 경로, 오류 원문, HTML, 쿠키, 프로필과 인증정보는 감사 JSON/API에 포함하지 않는다.

계측 범위는 `naver_store_hours_scheduled_run.py`뿐이다. `all_brands`, `new_targets`, Place ID 갱신·backfill을 정규 예약 이력으로 등록하지 않는다. Chrome 실행 방식, 포트 9233, 전용 프로필, 업무 SQL과 예약 설정을 변경하지 않는다.

## 실행·브랜드·시도 계약

감사 테이블의 한 행은 한 예약 실행의 한 브랜드다. `ParentRunId`로 두 브랜드를 묶고 `Payload.attempts`에 dry-run/Apply 단계별 최종 자식 실행 결과를 담는다. 실행/브랜드/단계 기록을 하나의 브랜드 snapshot으로 원자적으로 저장하여 단계 누락과 본문 버전 불일치를 줄인다.

- UUID namespace: `a354f224-e8ef-4ae1-9384-d78238004f78`.
- 부모 ID: UUID5(namespace, JSON 배열 `[source_instance, original_run_id]`, ASCII 직렬화, 공백 없음).
- 브랜드 ID: UUID5(parent, 원본 브랜드 코드).
- 실제 자식 보고가 있으면 브랜드·단계·coordinator 실행 ID·worker 실행 ID로 UUID5를 만들고 같은 최종 worker/attempt에 속한 매장만 집계한다.
- 고유 제약은 `(SourceInstance, OriginalRunId, BrandCode)`다. 같은 결과 재기록은 새 이력을 만들지 않는다. 완료 행은 늦게 도착한 시작/중간 관측으로 덮어쓰지 않는다.
- `SourceInstance`는 내부 실행 ID 생성에 사용하는 고정 논리 식별자다. 단일 운영 환경에서는 별도 설정 없이 기본값 `naver-crawler-prod`를 사용한다. 동일 서버 재배포 시 유지하고 다른 독립 설치에는 다른 값을 준다. 이를 바꾸면 UUID도 바뀌므로 임의 변경하지 않는다.
- 매장 코드는 문자열이며 선행 0을 보존한다. 매장별 checkpoint의 최종 결과만 집계한다. 이전 실패 시도 원문을 복원하지 않으며 최종 시도 번호와 자식 ID가 재시도 연결 근거다.
- 자식 보고 시각이 있으면 `timing_basis=worker-report`; 구버전 보고에 시각이 없으면 `parent-window`로 예약 실행 전체 관측 구간을 제공한다. 후자는 정확한 단계 시작·소요시간이 아니다.

과거 summary 파일을 임의로 찾아 감사 DB에 자동 backfill하지 않는다. 현재 예약 실행이 검증한 handoff, target set, dry-run digest, 완료 checkpoint만 전달한다. `.tmp`, 미완료/손상/다른 provenance 결과는 수용하지 않는다. 비정상 Apply도 같은 provenance 검사를 통과한 완료 checkpoint가 있으면 확인된 부분 반영을 감사 기록에만 보존하고 기존 성공 변경 CSV에는 포함하지 않는다.

## 상태·지표 대응

| 원본/근거 | 공통 표시 |
| --- | --- |
| 원본 `PARTIAL_FAILURE` | 공통 매핑 `PARTIAL_FAILED`; 브랜드별 품질 상태와 별도로 `raw_status` 보존 |
| 예약 SUCCESS + 검토 대상만 제외 | `WARNING` |
| 예약 SUCCESS + MATCH_FAILED/NO_HOURS/COLLECT_FAILED 제외 | `PARTIAL_FAILED` |
| 한 브랜드 Apply 일부 성공·실패 | 해당 브랜드 `PARTIAL_FAILED`, 확인된 반영 매장 집계 |
| Apply 실패이며 확인된 반영 없음 | 해당 브랜드 `FAILED`; 증거 부재 값은 null |
| 다른 브랜드 실패, 현재 브랜드 전부 확인 | 현재 브랜드 `SUCCESS`, 부모 원본 상태는 별도 보존 |
| 공통 preflight 실패 | 두 브랜드 `FAILED`, `PREFLIGHT_FAILED`, 대상 수 null |
| 검증된 전체 대상 0개 | `SUCCESS_EMPTY`, 대상/반영 0 |
| 안전 대상 0개지만 검토/실패 매장 존재 | WARNING/부분 실패, 반영 0; 전체 대상 0개와 구분 |
| `--preflight-only` | 실행 종류 `preflight-only`, 수집 건수 null, 성공 신선도 미갱신 |
| 시작만 관측 | `RUNNING`; 일정 정책 없으면 강제 종료로 추정하지 않음 |

| 필드 | 의미·단위 |
| --- | --- |
| `source_count` | 검증된 dry-run 전체 대상 매장 수 |
| `coverage_count` | dry-run에서 안전 상태로 영업시간 확인한 매장 수; Apply 성공률과 구분 |
| `review_count` | REVIEW_REQUIRED 매장 수 |
| `failure_count` | dry-run 실패와 최종 Apply 비안전 결과 매장 수. 미관측 실패를 임의 추정하지 않음 |
| `inserted_count/changed_count/unchanged_count` | 자식 실행 보고의 `db_applied`와 SAFE 결과 수가 일치하는 검증된 Apply 최종 매장 수 |
| `applied_count` | DB 반영이 확인된 매장 수. unknown과 0을 구분 |
| `successful_units/failed_units` | 확인된 Apply 성공 매장 / 관측된 실패 매장. dry-run 후보와 Apply 실패를 중복 합산하지 않음 |
| `committed` | 확인된 반영이 있으면 true, 검증된 미반영은 false, 근거 없으면 null. true는 전체 대상 완료를 뜻하지 않음 |
| 하위 dry-run 신규/변경/동일 | 예상 매장 수이며 상위 확정 반영 값으로 복사하지 않음 |
| `successful_check_at` | 정규 실행의 해당 브랜드 전체 대상 확인과 반영 근거가 갖춰진 완료 시각 |
| `latest_data_at` | 현재 null. 업무 테이블 시각 관측이 연결되지 않았으므로 추측하지 않음 |

업무 테이블은 매장당 7개 요일 행이다. `change_row_count`는 요일×변경 필드 상세 행 수이므로 위 매장 지표에 사용하지 않는다. 변경 0은 정상이다. NEW_STORE/UNCHANGED는 변경 CSV 대상이 아니다. `COLLECT_DT`는 UNCHANGED에도 갱신될 수 있어 마지막 업무값 변경 시각이나 전체 성공 근거로 사용하지 않는다. 브랜드별 신선도에는 성공 확인 시각과 최신 관측의 대상/커버리지를 각각 제공한다.

## 설정

기본 계측은 비활성이다. 크롤러 루트 `.env`를 읽고 프로세스 환경변수가 같은 키를 덮어쓴다. 값 보간은 하지 않는다. 비밀번호는 문서·로그·Git에 기록하지 않는다. 사용자가 지정한 기존 `.env`의 `NAVER_DB_HOST/USER/PASSWORD/NAME`을 감사 연결에서도 재사용한다. 감사 전용 `NAVER_STORE_HOURS_MONITORING_DB_HOST/USER/PASSWORD`가 하나라도 설정되면 세 값을 모두 요구하며 기존 계정과 혼합하지 않는다.

| 크롤러 환경변수 | 값 |
| --- | --- |
| `NAVER_STORE_HOURS_MONITORING_ENABLED` | 승인된 배포 시 `1` |
| `NAVER_STORE_HOURS_MONITORING_SOURCE_INSTANCE` | 선택 사항. 미설정 시 내부 기본값 `naver-crawler-prod`; 이미 지정한 값은 유지 |
| `NAVER_STORE_HOURS_MONITORING_TIMEZONE` | 실제 실행 호스트의 확인된 IANA 시간대; 확인 후 예: `Asia/Seoul` |
| `NAVER_STORE_HOURS_MONITORING_DB_HOST` | 선택적 별도 감사 DB 호스트 |
| `NAVER_STORE_HOURS_MONITORING_DB_USER` | 선택적 별도 감사 기록 계정 |
| `NAVER_STORE_HOURS_MONITORING_DB_PASSWORD` | 별도 감사 계정 사용 시 함께 지정 |

DB 이름은 `naverDB`로 고정한다. 별도 pymssql 연결, 3초 로그인/쿼리·잠금 제한을 사용한다. 기록 오류는 `STORE_HOURS_MONITORING_UNAVAILABLE`만 로그에 남기며 업무 트랜잭션·Apply 판단·종료 코드·재시도·프로세스 정리를 바꾸지 않는다. naive summary 시각은 명시된 호스트 시간대를 적용한 뒤 UTC로 변환하며 DST 중복/존재하지 않는 시각은 추측하지 않는다. SQL datetime2는 이 계측이 이미 UTC로 변환한 값이다.

플랫폼은 `MONITORING_NAVER_STORE_HOURS_CONNECTION_STRING`만 설정해도 과거 관측 이력을 조회한다. 별도 SELECT 전용 계정과 `ApplicationIntent=ReadOnly`를 사용한다. 일정 미확인 상태에서는 아래 여섯 값을 모두 비운영/미설정으로 둔다.

- `MONITORING_NAVER_STORE_HOURS_SCHEDULE_TIMEZONE`
- `MONITORING_NAVER_STORE_HOURS_WEEKLY_SCHEDULED_DAY`: 월요일 0 ~ 일요일 6
- `MONITORING_NAVER_STORE_HOURS_WEEKLY_SCHEDULED_TIME`: 시간대 없는 현지 예정 시각
- `MONITORING_NAVER_STORE_HOURS_START_GRACE_MINUTES`: 양수
- `MONITORING_NAVER_STORE_HOURS_MAX_DURATION_MINUTES`: 양수
- `MONITORING_NAVER_STORE_HOURS_SCHEDULE_ATTRIBUTION_WINDOW_MINUTES`: 시작 유예 이상, 10,080분 미만

실제 등록된 요일·시각·시간대·유예·실행 제한을 운영 담당자가 확인한 뒤 여섯 값을 함께 설정한다. 문서의 주간 권장/6시간 권장은 기본값으로 활성화하지 않는다. 정책은 유예가 지난 최근 주간 회차에 실제 시작이 `[예정 시각, 예정 시각+귀속 창)`에 있는지를 판단한다. 현재 카드에서 미관측 브랜드는 NOT_RUN, 최대 실행시간이 지난 RUNNING은 ABORTED로 표시한다. 이는 읽기 시점 정책 판정이며 감사 원본·과거 이력/상세를 변경하지 않는다. 계측 누락과 실제 강제 종료를 확정적으로 구별하지 못한다. 설정 없이 저장된 이력이 아예 없을 때 기존 플랫폼의 NOT_RUN/빈 최신 실행 표시는 단순 관측 이력 부재이며 주간 지연 경보가 아니다.

## DBA 검토·권한

크롤러 저장소 `scripts/sql/store_hours_monitoring/01_create.sql`, `02_verify.sql`을 검토한다. 운영 적용은 별도 승인 대상이다. SQL Server 2016 이상 JSON 기능이 필요하다.

1. 대상 naverDB, 백업·복구 계획, 감사 테이블 이름 충돌, 인덱스·고유키·CHECK 제약을 확인한다.
2. DBA가 승인된 창에서 create를 적용한다. 기존 객체가 있으면 자동 재생성하지 않고 중단한다.
3. verify를 실행하여 컬럼, 고유키, 상태/시간/JSON/브랜드 제약을 확인한다.
4. 감사 전용 계정을 발급하는 경우 이 테이블의 SELECT/INSERT/UPDATE만 허용한다. 현재 사용자는 크롤러 `.env`의 기존 master 계정 재사용을 지정했다. 구현은 계정 재사용 여부와 무관하게 업무 트랜잭션과 별도 연결을 사용한다.
5. API 계정에는 이 테이블의 SELECT만 허용한다. DB/server role 상속으로 DML·DDL을 얻지 않는지 각 principal의 verify 권한 조회로 검토한다. ApplicationIntent는 DB 권한을 대체하지 않는다.
6. 기존 업무 테이블, SmartPlace 감사 테이블과 예약 작업 권한은 확장하지 않는다.

## 배포·첫 정규 회차 확인

구현/fixture 검증은 배포 승인이 아니다. 운영 배포, DB DDL, 예약 변경, 실제 크롤러 실행, 메일은 이번 작업에서 수행하지 않는다.

1. DBA DDL/권한 검토 및 적용을 별도 승인받는다.
2. 크롤러 계측 코드를 배포하고 실제 호스트 시간대 및 전용 감사 환경을 주입한다. 기존 예약/브라우저 설정은 유지한다.
3. 플랫폼 API/웹을 배포하고 SELECT 전용 연결을 주입한다. 일정은 확인 전 비활성화한다.
4. 별도 승인된 조회 smoke에서 live/readiness, collectors/runs/detail/freshness를 확인한다. 새 소스 장애가 기존 FC다움/HMR/SmartPlace 조회를 가리지 않는지 확인한다.
5. 다음 정상 예약 회차를 기다린다. 대시보드에서 실행하지 않는다.
6. 원본 summary와 브랜드 UUID/부모 ID, 원본 상태, 검토·실패·전체 대상, dry-run 예상/Apply 확정 매장 수, 최종 worker 시도 번호를 대조한다.
7. 변경 CSV 상세 행 수와 변경 매장 수를 혼동하지 않는다. DB 실제 반영은 승인된 SELECT로 확인하고 전체 대상 커버리지와 구분한다.
8. 새로고침을 반복해 동일 UUID 행이 중복 생성되지 않는지, 브랜드 필터·부분 실패·null 표시를 확인한다.

## 관측 한계와 보존

시작 기록 전 강제 종료 또는 감사 연결 실패는 실행 자체를 누락시킬 수 있다. 시작은 기록됐지만 완료 저장에 실패하면 RUNNING이 남을 수 있다. 이 상태에서 업무 DB 반영은 성공했을 수도 있으므로 운영자는 기존 로그/summary와 업무 데이터를 별도로 대조한다. 감사 기록 장애를 업무 실패로 보정하지 않는다.

summary는 권위 있는 최종 산출물이다. optional 완료 마커 부재/쓰기 실패는 유효한 summary의 종료 관측을 취소하지 않는다. summary 발행 자체를 검증하지 못하면 확정 종료 감사 이벤트를 만들지 않는다. 정규 실행 밖의 수동 실행과 이전 90일 파일을 자동 수집하지 않는다.

크롤러 산출물의 기존 90일 보존 정책은 유지한다. 감사 DB의 보존은 이 파일 정리와 독립적이며 이 구현은 감사 행을 자동 삭제하지 않는다. DBA가 감사량·회사 보존 기준에 따라 최소 필요한 기간, 백업과 삭제 작업을 별도 승인한다.

## 롤백

1. 크롤러 환경의 `NAVER_STORE_HOURS_MONITORING_ENABLED`를 해제하거나 계측 전 artifact로 되돌린다. 업무 데이터/예약/브라우저 설정은 유지한다.
2. API에서 `MONITORING_NAVER_STORE_HOURS_CONNECTION_STRING`과 주간 정책 주입을 제거하거나 이전 artifact로 되돌린다.
3. 필요한 경우 웹 artifact를 이전 버전으로 되돌린다. 기존 세 소스 조회를 확인한다.
4. 감사 테이블/행은 삭제하지 않는다. 잔여 프로세스 종료를 확인한 뒤 감사 쓰기 권한 회수를 별도로 승인한다.

## 비운영 검증

크롤러: `python -m pytest tests/test_naver_store_hours_*.py`에 해당하는 파일 목록을 PowerShell에서 확장하여 실행한다. 신규 계측 테스트는 `tests/test_naver_store_hours_monitoring.py`다. API는 루트 `.env`가 테스트에 유입되지 않도록 `apps/api` 디렉터리에서 `python -m pytest tests`, 웹은 `npm test -- --run`, `npm run lint`, `npm run typecheck`, `npm run build`를 수행한다. 테스트에서는 실제 네이버 접속/업무 DB 쓰기를 사용하지 않는다. 실행 결과와 환경 제약은 구현 검증 보고서에 기록한다.
## 적용 진행 기록

- 2026-09-10: 사용자로부터 DDL 적용 완료를 전달받았다. 에이전트가 운영 DB에 DDL을 실행하거나 실제 스키마를 조회해 검증한 결과는 아니다.
- 다음 확인: `02_verify.sql`의 컬럼/제약/권한 결과, 감사 기록 계정과 API SELECT 전용 계정 준비, 크롤러·플랫폼 배포 및 환경변수 주입.
- 실제 예약 설정과 첫 정규 회차 대조는 아직 확인되지 않았다.
- 2026-09-10 계정 설정 후속 확인: 사용자는 크롤러 `.env`의 기존 master 계정과 플랫폼 `.env`의 readonly 계정을 지정했다. 크롤러 계측의 `.env` 로딩/기존 NAVER_DB 설정 재사용을 추가했다. 플랫폼 SmartPlace/영업시간 연결 문자열 끝의 잘못된 따옴표만 제거했으며 자격증명은 변경하지 않았다. ReadOnly 연결 의도 검증은 통과했다. 실제 DB principal 권한 조회 결과는 아직 없다. 계측 활성화·source instance·운영 호스트 시간대는 변경하지 않았다.

- 고정 식별자는 사용자 필수 설정에서 제외했다. 미설정 시 내부 기본값을 사용하며 기존 지정값과 감사 테이블 구조는 유지한다.
