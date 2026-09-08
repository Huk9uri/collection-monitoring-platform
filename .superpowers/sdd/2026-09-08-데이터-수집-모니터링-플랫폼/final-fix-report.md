# 데이터 수집 모니터링 플랫폼 최종 수정 보고서

## 1. 범위와 결론

- 모니터링 기준 커밋: `5a25641`
- 최종 리뷰의 Critical 1건, Important 5건, Minor 5건을 모두 수정했다.
- 기존 읽기 전용 API, 자동 polling 없음, 사용자 수동 새로고침, 한 소스 장애 시
  부분 응답, 저장 이력 상태 필터, 전역 정렬·페이지네이션 계약을 유지했다.
- FC다움 외부 폴더는 Git 저장소로 만들거나 커밋하지 않았다. 변경 전 snapshot
  `final-fix-fc-before`와 비교해 `crawling.py`, `tests/test_crawling.py` 두 파일만
  변경됐다.
- 실제 수집, DDL/DML, 외부 API, 실제 DB smoke는 실행하지 않았다.

## 2. 리뷰 finding별 변경과 검증

### C1. HMR `SUCCESS_WITH_DATA` 성공 계약

- HMR run/attempt canonical SQL의 성공 집합에 실제 생산자 토큰
  `SUCCESS_WITH_DATA`를 포함했다. latest, list, count, status filter, summary 집계,
  상세, 재시도 판정이 같은 어휘를 사용한다.
- 공통 `CollectorAttempt.outcome`을 추가해 adapter가 원시 상태를 canonical
  상태로 바꾸고, 서비스와 web은 원시 문자열을 다시 해석하지 않게 했다.
- Python raw-run fallback도 `SUCCESS_WITH_DATA`를 `SUCCESS`로 처리한다.
- web 상세는 `outcome`만으로 성공·실패·주의를 표시한다.
- 검증: `test_hmr_adapter.py`의 실제 HMR 어휘 기반 전부 성공, 데이터 있음과 빈
  성공 혼합, 실패 후 재시도 성공, list/count/filter/detail 및 raw fallback 회귀;
  `run-detail-sheet.test.tsx`의 canonical outcome 표시 회귀.

### I1. 시간 기반 collector overview 정책

- 수집기별 schedule timezone과 일일 예정 시각, 최대 실행시간, 데이터셋별
  freshness SLA를 환경변수로 명시했다. 실제 운영값을 추측하지 않으며 미설정
  정책은 저장 상태를 유지한다.
- schedule timezone과 시각은 반드시 함께 설정하고, 알려진 고정 데이터셋 외
  SLA 이름은 기동 시 거부한다. Windows에서도 IANA timezone이 동작하도록 API
  의존성에 `tzdata`를 추가했다.
- 주입 clock으로 `/collectors`에서만 동적 상태를 계산한다. 오늘 예정 시각 뒤
  이력 없음 또는 마지막 실행이 이전 예정일이면 `NOT_RUN`, 최대 실행시간을 넘긴
  저장 `RUNNING`은 `ABORTED`, 데이터 변경 시각이 SLA를 넘기면 `WARNING`이다.
  stale `RUNNING`의 `ABORTED` 판정은 missed schedule보다 우선한다.
- `latest_run.status`와 `/runs` 상태·필터·count는 저장된 canonical 이력을 그대로
  유지해 과거 run을 변조하지 않는다.
- `last_successful_check_at`과 `latest_data_at`을 분리하고 SLA 및 초과 여부를
  DTO와 UI 레이블로 노출했다.
- 검증: 고정 UTC clock 기반 이력 없음, 어제 성공 뒤 오늘 missed schedule,
  stale running, stale freshness, 정책 미설정, history 비변조 테스트.

### I2. 서울 날짜 기준 `/summary`와 KPI

- `/summary`를 collector latest 목록이 아닌 명시적 aggregate DTO로 변경했다.
  `overall_status`, 등록 수집기 수, 오늘 `SUCCESS`/`SUCCESS_EMPTY` 실행 수,
  오늘 `PARTIAL_FAILED`/`FAILED`/`ABORTED` 실행 수, 실행 중 수를 반환한다.
- Asia/Seoul 현지 자정의 반개구간 `[오늘 00:00, 다음날 00:00)`을 UTC SQL
  parameter로 변환한다. 전체 상태는 같은 오늘 집계에서 가장 높은 장애 등급을
  사용한다.
- web KPI는 summary만 사용한다. collector 카드와 신선도는 `/collectors`의 한
  snapshot을 사용하고, 이력 표만 `/runs`를 유지한다. 따라서 화면은
  `/summary`, `/collectors`, `/runs` 세 요청이며 중복 `/freshness` 호출은 없다.
- 검증: 같은 날 실패 후 성공을 각각 집계, 전날 실패 제외, 서울 자정 포함/제외
  경계, web KPI 및 수동 refresh 세 요청 회귀.

### I3. 전체 관측 불능 계약

- 모든 응답에 등록·성공·실패 source 수와 `all_sources_unavailable`을 갖는
  `source_status`를 추가했다. 등록 source가 0개이거나 모든 adapter가 실패하면
  전체 관측 불능이며, 하나만 실패하면 HTTP 200 부분 장애를 유지한다.
- web은 HTTP/Zod 실패뿐 아니라 이 metadata를 사용해 전체 오류와 부분 장애를
  구분한다.
- 검증: 두 source 모두 실패, 한 source만 실패, source 0개, 상세 source 실패,
  오류 응답의 비밀·SQL 비노출 API/web 회귀.

### I4. timeout, 병렬 격리와 정리

- 양수 DB connect/login timeout, statement query timeout, source 공통 deadline,
  Axios timeout을 설정화했다. 기본값은 각각 5초, 30초, 35초, 40,000ms다.
- `ReadOnlyRepository`는 connect timeout을 driver에 전달하고 connection query
  timeout을 설정한다. 성공·실패·timeout 모두 cursor와 connection을 `finally`로
  닫는다.
- source 호출은 source별 bulkhead semaphore 안의 daemon 작업으로 병렬
  실행하고 공통 deadline까지만 기다린다. Python 종료 시 hung worker를 join하는
  `ThreadPoolExecutor`를 사용하지 않는다. 한 source의 반복 hang은 해당 source의
  고정 슬롯까지만 차지하며 다른 정상 source 슬롯을 고갈시키지 않는다.
- web Axios timeout은 API source deadline보다 길어 부분 응답 기회를 보존한다.
- 검증: 실제 sleep 없는 fake thread/future로 정상 peer 반환, common deadline,
  반복 hung 상한과 healthy source starvation 방지, 반복 readiness, DB timeout 전달,
  cursor/connection cleanup, 양수 설정 및 Axios override 테스트.

### I5. FC다움 감사 완전성

- FC다움 `run_all_brands`가 각 `record_attempt` 안전 호출의 성공 여부를 누적한다.
  시도 한 건이라도 저장되지 않으면 업무 성공/실패 종료 코드와 기존 출력은
  유지하되 `finish_run`의 원시 상태를 보수적으로 `ABORTED`로 기록한다.
- 예상치 못한 예외 경로와 최종 업무 실패 경로에도 같은 규칙을 적용한다.
- 모니터링 adapter는 raw `ABORTED`와 저장 run 성공/실패 건수를 남아 있는 attempt
  재계산보다 우선해 부분 감사 유실을 성공으로 덮지 않는다.
- 검증: 첫 attempt write만 실패 후 후속 attempt와 finish 성공, 마지막 실패
  attempt write 유실에도 업무 exit code 1 보존, 예상치 못한 예외, adapter의 raw
  `ABORTED` 우선 회귀 및 FC다움 전체 테스트.

### M1. UUID 경계

- `CollectorRun.run_id`, adapter/service와 FastAPI path를 UUID로 통일하고 SQL
  parameter 직전에 문자열로 변환한다. web Zod 및 모든 fixture도 실제 UUID를
  사용한다.
- 검증: malformed path는 adapter 호출 전 422, 유효하지만 없는 UUID는 404,
  OpenAPI UUID format, web 요청 조건 검증.

### M2. exact CORS origin

- `*`, HTTP(S) 이외 scheme, host 없음, userinfo, path, query, fragment, 잘못된
  port와 빈 port를 Settings 생성 시 거부한다. middleware에는 검증된 exact
  origin만 전달한다.
- 검증: 허용 origin preflight와 각 거부 사례 설정 테스트.

### M3. HMR 실패 attempt의 commit 불확실성

- HMR 감사 스키마가 commit 사실을 제공하지 않으므로 성공 토큰만
  `committed=true`, 실패는 `null`로 합성한다. 성공 판정은 canonical outcome과
  결합해 `SUCCESS_WITH_DATA` 회귀를 막는다.
- 검증: SQL projection과 API/web nullable schema 회귀.

### M4. URL과 요청 상태 정규화

- 최초 진입과 `popstate`에서 invalid 날짜·상태를 제거하고 page를 서버 허용
  범위로 clamp한 canonical URL을 `replaceState`한다. 서버 total이 더 작으면 실제
  마지막 page로 다시 교정한다.
- 역전 날짜와 93일 초과 범위는 실행 이력 요청 전에 필드 인접 오류로 표시하고
  해당 요청을 보내지 않는다. 유효한 filter와 global pagination 계약은 유지한다.
- 검증: invalid/reversed/>93일, page 999, 서버 total 보정, 뒤로가기,
  URL·UI·request 일치 테스트.

### M5. positive 상태 대비

- `positive-foreground`와 `positive-surface` semantic token을 light/dark theme에
  추가하고 정상 badge와 KPI 아이콘에 사용했다.
- 검증: 두 theme의 foreground/background 조합을 실제 상대 휘도 공식으로 계산해
  일반 텍스트 WCAG AA 4.5:1 이상임을 테스트한다.

## 3. 최종 검증

| 범위 | 명령/방법 | 결과 |
| --- | --- | --- |
| API 전체 | `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests -p no:cacheprovider -q` | 157 passed |
| API compile | `python -m compileall -q apps/api/src` | 성공 |
| web 테스트 | `npm --workspace apps/web test` | 70 passed |
| web 타입 | `npm --workspace apps/web run typecheck` | 성공 |
| web lint | `npm --workspace apps/web run lint` | 경고 없이 성공 |
| web build | `npm --workspace apps/web run build` | 2,135 modules, 성공 |
| FC다움 전체 | FC다움 venv `pytest -p no:cacheprovider --basetemp=... -q` | 139 passed |
| HMR 관련 | HMR 자체 의존성 환경에서 orchestrator/audit/database/audit SQL 테스트 | 26 passed |
| 변경 형식 | `git diff --check` | 성공 |
| 최종 코드 재리뷰 | API 집중 재리뷰와 전체 diff 통합 재리뷰 | 두 리뷰 모두 잔존 Critical/Important/Minor 0건 |

HMR venv에는 pytest runner가 설치되어 있지 않아, HMR 자체 venv와 설치된 생산자
의존성은 그대로 사용하고 로컬 FC다움 검증 환경의 pytest package만
`PYTHONPATH`로 주입했다. 관련 테스트는 모두 mock/fake 경계에서 실행됐고 실제
수집·DB·외부 API를 호출하지 않았다.

## 4. 운영 반영 전 남은 확인사항

전용 `MONITORING_FCDAUM_CONNECTION_STRING`과
`MONITORING_HMR_CONNECTION_STRING`이 없으므로 실제 DB smoke는 의도적으로
수행하지 않았다. 이는 코드 미완료가 아니라 별도 운영 gate다. 운영 반영 전에는
다음을 확인해야 한다.

1. DBA가 FC다움 080 DDL을 적용하고 085 SELECT-only 검증을 DBA와 실제 읽기 전용
   principal로 각각 수행한다.
2. 전용 비밀 저장소의 두 연결 문자열로 readiness, collectors, runs, 대표 상세와
   상태 필터를 순서대로 smoke한다.
3. 실제 ODBC/TLS 및 SQL Server에서 오늘 canonical 집계와 HMR 8개 freshness
   `MAX(CollectedAt)`의 실행계획·지원 인덱스를 데이터 증가량 기준으로 확인한다.
4. 실제 scheduler 시간, 최대 실행시간과 데이터셋 SLA를 운영 소유자가 확인한 뒤
   환경변수로 주입한다. 확인 전에는 값을 추측하지 않는다.
5. 로그인 범위 밖의 MVP이므로 사내망·방화벽·reverse proxy 접근 제한을 확인한다.
6. Git이 아닌 FC다움 배포 자산에는 snapshot diff의 두 변경 파일을 provenance와
   함께 반영한다.
