# SmartPlace 사후 수집 모니터링 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**목표:** SmartPlace 실제 수집 결과를 브랜드별 실행과 `login`·`normal`·`pos_linked` 하위 작업으로 naverDB에 기록하고 기존 읽기 전용 대시보드에서 조회한다.

**아키텍처:** `naver_crawling`은 업무 적재 트랜잭션과 분리된 감사 저장소로 실행·시도를 기록한다. `collection-monitoring-platform`의 SmartPlace 어댑터는 이를 SELECT 전용으로 공통 모델에 정규화하고 React 화면은 브랜드별 행과 기존 상세 패널을 표시한다.

**기술 스택:** Python 3.12, pymssql, SQL Server, FastAPI, Pydantic, pytest, React, TypeScript, Zod, Vitest

**설계:** `docs/설계/2026-09-09-smartplace-사후-수집-모니터링.md`

## 전역 제약

- 대시보드와 API는 크롤러 실행·중지·재실행 및 작업 스케줄러 조작을 하지 않는다.
- API는 수집기 DB를 읽기 전용 계정으로 조회하고 HMR·FC다움 스키마를 변경하지 않는다.
- 비밀번호, 쿠키, 토큰, HTML, SQL 원문과 traceback을 DB·API에 저장하거나 노출하지 않는다.
- 알 수 없는 집계는 `0`이 아니라 `NULL`로 보존한다.
- 업무 데이터와 모니터링 트랜잭션을 분리하며 모니터링 실패가 수집 결과를 바꾸지 않는다.
- 화면 유형은 명시적 작업 설정이나 확인된 분류 결과로만 기록하고 추측하지 않는다.
- 운영 DDL·권한·배포·예약 실행은 별도 운영자 승인 전에는 수행하지 않는다.

---

### Task 1: SmartPlace 실행 이력 SQL 계약

**Files:**
- Create: `C:/workspace/naver_crawling/scripts/sql/smartplace_monitoring/01_create.sql`
- Create: `C:/workspace/naver_crawling/scripts/sql/smartplace_monitoring/02_verify.sql`
- Create: `C:/workspace/naver_crawling/tests/test_smartplace_monitoring_sql.py`

**Interfaces:**
- Produces: `dbo.SMARTPLACE_COLLECTION_RUN`, `dbo.SMARTPLACE_COLLECTION_ATTEMPT`
- Consumes: SQL Server `uniqueidentifier`, `datetime2`, FK·CHECK·UNIQUE 제약

- [ ] **Step 1: 생성·검증 계약의 실패 테스트 작성**

```python
def test_schema_has_brand_run_and_unit_attempt_contract():
    sql = APPLY_SQL.read_text(encoding="utf-8")
    for token in (
        "SMARTPLACE_COLLECTION_RUN", "SMARTPLACE_COLLECTION_ATTEMPT",
        "UNIQUE (ScheduledAt, BrandCode)",
        "PRIMARY KEY (RunId, UnitCode, AttemptNo)", "FOREIGN KEY (RunId)",
    ):
        assert token in sql

def test_unknown_counts_are_nullable():
    sql = APPLY_SQL.read_text(encoding="utf-8")
    assert "SourceCount int NULL" in sql
    assert "ErrorSummary nvarchar(500) NULL" in sql
```

- [ ] **Step 2: 테스트가 파일 부재로 실패하는지 확인**

Run: `python -m pytest tests/test_smartplace_monitoring_sql.py -q`
Expected: FAIL because `01_create.sql` does not exist.

- [ ] **Step 3: 멱등 DDL과 읽기 전용 검증 SQL 구현**

`01_create.sql`은 각 대상에 대한 `IF OBJECT_ID(N'dbo.테이블명', N'U') IS NULL`
경계 안에서 두 테이블, PK, FK,
`(ScheduledAt, BrandCode)` UNIQUE와 상태·건수 CHECK를 만든다. `02_verify.sql`은
`sys.tables`, `sys.columns`, `sys.key_constraints`, `sys.foreign_keys`,
`sys.check_constraints`만 SELECT하고 DML을 포함하지 않는다.

- [ ] **Step 4: SQL 계약 테스트 통과 확인**

Run: `python -m pytest tests/test_smartplace_monitoring_sql.py -q`
Expected: PASS.

- [ ] **Step 5: Task 1 커밋**

```powershell
git add scripts/sql/smartplace_monitoring tests/test_smartplace_monitoring_sql.py
git commit -m "feat: define SmartPlace monitoring schema"
```

### Task 2: 크롤러용 감사 저장소와 오류 정제

**Files:**
- Create: `C:/workspace/naver_crawling/scripts/python/smartplace_monitoring.py`
- Create: `C:/workspace/naver_crawling/tests/test_smartplace_monitoring.py`

**Interfaces:**
- Produces: `RunIdentity`, `SmartPlaceMonitoringRepository`
- Produces: `start_run`, `start_attempt`, `finish_attempt`, `finish_run`
- Produces: `sanitize_error_summary(value: object) -> str`

- [ ] **Step 1: 상태 전이와 redaction 실패 테스트 작성**

```python
def test_start_run_commits_running_brand_row(connection):
    repository = SmartPlaceMonitoringRepository(lambda: connection)
    identity = repository.start_run(
        scheduled_at=datetime(2026, 9, 10, 4), brand_code="hanchon",
        brand_name="한촌설렁탕", correlation_id="20260910-040000-hanchon",
    )
    assert identity.brand_code == "hanchon"
    connection.commit.assert_called_once()

def test_error_summary_removes_credentials_and_limits_length():
    summary = sanitize_error_summary(
        "password=secret cookie=session-token " + "x" * 700
    )
    assert "secret" not in summary and "session-token" not in summary
    assert len(summary) <= 500
```

- [ ] **Step 2: 테스트가 모듈 부재로 실패하는지 확인**

Run: `python -m pytest tests/test_smartplace_monitoring.py -q`
Expected: FAIL with module import error.

- [ ] **Step 3: 독립 연결·commit 저장소 구현**

`RunIdentity`는 `run_id: UUID`, `scheduled_at: datetime`, `brand_code: str`을 가진
불변 dataclass로 만든다. 저장소에는 테스트에서 사용한 정확한 키워드 인자를 받는
`start_run() -> RunIdentity`, `start_attempt() -> int`, `finish_attempt() -> None`,
`finish_run() -> None`을 구현한다. 각 메서드는 새 연결과 독립 commit을 사용하며
예외 시 rollback·close한다. 재실행은
`ScheduledAt + BrandCode` 기존 `RunId`를 잠금 조회하고 `AttemptNo`를 증가시킨다.

- [ ] **Step 4: 저장소 집중 테스트 통과 확인**

Run: `python -m pytest tests/test_smartplace_monitoring.py -q`
Expected: PASS.

- [ ] **Step 5: Task 2 커밋**

```powershell
git add scripts/python/smartplace_monitoring.py tests/test_smartplace_monitoring.py
git commit -m "feat: record SmartPlace monitoring lifecycle"
```

### Task 3: SmartPlace 실행 흐름 계측

**Files:**
- Modify: `C:/workspace/naver_crawling/scripts/python/smartplace_crawler_V2.2_jadong.py`
- Modify: `C:/workspace/naver_crawling/tests/test_smartplace_crawler_v22.py`

**Interfaces:**
- Consumes: Task 2의 `SmartPlaceMonitoringRepository`
- Produces: `classify_monitoring_error(exc, *, page_signal=None) -> str`

- [ ] **Step 1: 브랜드 집계와 단계별 실패 테스트 추가**

```python
def test_login_failure_marks_remaining_units_not_run():
    recorder = FakeMonitoringRecorder()
    assert run_account_job(login_fails_job(), DATES, recorder=recorder) is False
    assert recorder.units == [
        ("login", "FAILED", "LOGIN_FAILED"),
        ("normal", "NOT_RUN", "PREREQUISITE_FAILED"),
        ("pos_linked", "NOT_RUN", "PREREQUISITE_FAILED"),
    ]

def test_verified_protection_page_uses_account_protected():
    assert classify_monitoring_error(
        RuntimeError("login rejected"), page_signal="account_protected"
    ) == "ACCOUNT_PROTECTED"
```

- [ ] **Step 2: 테스트가 recorder 인터페이스 부재로 실패하는지 확인**

Run: `python -m pytest tests/test_smartplace_crawler_v22.py -q`
Expected: FAIL on the new monitoring contract.

- [ ] **Step 3: 실제 단계 경계에 최소 계측 추가**

`main()`은 예정 시각과 브랜드별 recorder를 만들고 `run_account_job()`은 브라우저,
로그인, 수집/파싱, DB 저장의 확인된 결과를 기록한다. 여러 한촌 계정은 동일 브랜드
`RunId` 아래 시도를 누적한다. `normal`·`pos_linked`는 job의 명시적
`monitoring_unit_code` 또는 확인된 화면 분류만 허용하고 둘 다 없으면 `UNKNOWN`으로
실패시켜 임의 분류를 막는다.

오류 매핑은 확인된 실행 단계와 신호를 사용한다. 보호조치 화면은
`ACCOUNT_PROTECTED`, 그 외 인증 거절은 `LOGIN_FAILED`, WebDriver 생성·세션 오류는
`BROWSER_FAILED`, 페이지 응답·탐색 오류는 `PAGE_LOAD_FAILED`, 의미 값 추출 실패는
`PARSE_FAILED`, 업무 commit 실패는 `DB_FAILED`, 최상위 미분류 예외는
`PROCESS_CRASHED`, 명시적 제한시간 초과는 `TIMEOUT`, 앞 단계 실패로 건너뛴 작업은
`PREREQUISITE_FAILED`로 기록한다.

```python
def record_safely(action, *, logger):
    try:
        action()
    except Exception as exc:
        logger.warning("SmartPlace monitoring record failed: %s",
                       type(exc).__name__)
```

- [ ] **Step 4: SmartPlace 회귀 테스트 통과 확인**

Run: `python -m pytest tests/test_smartplace_monitoring.py tests/test_smartplace_crawler_v22.py tests/test_smartplace_browser.py tests/test_smartplace_parsers.py -q`
Expected: PASS.

- [ ] **Step 5: Task 3 커밋**

```powershell
git add scripts/python/smartplace_crawler_V2.2_jadong.py tests/test_smartplace_crawler_v22.py
git commit -m "feat: instrument SmartPlace collection outcomes"
```

### Task 4: 공통 API 모델의 브랜드 범위와 nullable 집계

**Files:**
- Modify: `apps/api/src/monitoring_api/adapters/base.py`
- Modify: `apps/api/tests/test_models.py`
- Modify: `apps/api/tests/test_hmr_adapter.py`
- Modify: `apps/api/tests/test_fcdaum_adapter.py`
- Modify: `apps/web/src/features/monitoring/data/schema.ts`
- Modify: `apps/web/src/features/monitoring/data/schema.test.ts`

**Interfaces:**
- Produces: `CollectorRun.scope_id: str | None`, `scope_name: str | None`
- Produces: nullable 집계 네 필드
- Consumes: 기존 수집기 scope는 `None`, 기존 정수 집계는 유지

- [ ] **Step 1: API와 Zod 계약 실패 테스트 작성**

```python
def test_run_preserves_scope_and_unknown_counts():
    run = CollectorRun(scope_id="hanchon", scope_name="한촌설렁탕",
                       source_count=None, inserted_count=None,
                       changed_count=None, unchanged_count=None, **BASE_RUN)
    assert run.scope_name == "한촌설렁탕" and run.source_count is None
```

```typescript
expect(collectorRunSchema.parse(smartplaceRun)).toMatchObject({
  scope_id: 'hanchon', scope_name: '한촌설렁탕', source_count: null,
})
```

- [ ] **Step 2: 현재 계약에서 실패하는지 확인**

Run: `python -m pytest apps/api/tests/test_models.py apps/api/tests/test_hmr_adapter.py apps/api/tests/test_fcdaum_adapter.py -q`

Run: `npm test -- --run apps/web/src/features/monitoring/data/schema.test.ts`

Expected: FAIL on missing scope or nullable count rejection.

- [ ] **Step 3: 공통 모델과 변환기를 최소 확장**

집계를 `int | None`으로 바꾸고 합계는 선택된 시도의 모든 값이 확인될 때만
계산한다. `run_from_row()`은 scope 별칭이 없는 기존 행에 `None`을 사용한다. Zod도
`.nullable()`로 맞춘다.

- [ ] **Step 4: API·웹 모델 회귀 통과 확인**

Run: `python -m pytest apps/api/tests/test_models.py apps/api/tests/test_hmr_adapter.py apps/api/tests/test_fcdaum_adapter.py -q`

Run: `npm test -- --run apps/web/src/features/monitoring/data/schema.test.ts`

Expected: PASS.

- [ ] **Step 5: Task 4 커밋**

```powershell
git add apps/api/src/monitoring_api/adapters/base.py apps/api/tests apps/web/src/features/monitoring/data
git commit -m "feat: add monitoring run scope"
```

### Task 5: SmartPlace 읽기 전용 어댑터와 일정 정책

**Files:**
- Create: `apps/api/src/monitoring_api/adapters/smartplace.py`
- Create: `apps/api/tests/test_smartplace_adapter.py`
- Modify: `apps/api/src/monitoring_api/config.py`
- Modify: `apps/api/src/monitoring_api/composition.py`
- Modify: `apps/api/tests/test_composition.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `SmartPlaceAdapter(collector_id="smartplace")`
- Consumes: Task 1 테이블과 SmartPlace 일정·예상 scope 설정

- [ ] **Step 1: 어댑터·설정·합성 실패 테스트 작성**

```python
def test_list_runs_returns_one_row_per_brand_with_attempts(repository):
    runs = SmartPlaceAdapter(repository).list_runs(limit=20)
    assert [(r.scope_id, [a.unit_id for a in r.attempts]) for r in runs] == [
        ("hanchon", ["login", "normal", "pos_linked"]),
        ("yuksoodang", ["login", "normal", "pos_linked"]),
    ]

def test_missing_expected_brand_is_not_run_after_grace(repository, clock):
    runs = SmartPlaceAdapter(repository, policy=POLICY, clock=clock).list_runs(limit=20)
    assert runs[0].scope_id == "yuksoodang"
    assert runs[0].status is MonitoringStatus.NOT_RUN
```

- [ ] **Step 2: 어댑터 부재로 실패하는지 확인**

Run: `python -m pytest apps/api/tests/test_smartplace_adapter.py apps/api/tests/test_composition.py -q`
Expected: FAIL with missing adapter/config fields.

- [ ] **Step 3: 고정 SELECT 어댑터와 정책 구현**

HMR·FC다움의 bulk attempt 조회를 따라 N+1 쿼리를 피한다. 최종 `AttemptNo`만 상태에
반영한다. `NOT_RUN`과 stale `RUNNING`은 주입된 UTC clock으로 계산하고 DML을 하지
않는다. 승인된 SmartPlace 업무 신선도 쿼리가 아직 없으므로 `freshness()`는 빈
목록을 반환하고 최신 성공 시각은 성공한 브랜드 실행의 `FinishedAt`으로 계산한다.
`.env.example`에 다음 비밀값 없는 예시 계약을 추가한다.

```dotenv
MONITORING_SMARTPLACE_CONNECTION_STRING=Driver={ODBC Driver 17 for SQL Server};Server=monitoring-db.example.internal;Database=naverDB;UID=monitoring_reader;PWD=secret-from-secure-store;Encrypt=yes;TrustServerCertificate=no;ApplicationIntent=ReadOnly
MONITORING_SMARTPLACE_SCHEDULE_TIMEZONE=Asia/Seoul
MONITORING_SMARTPLACE_DAILY_SCHEDULED_TIME=04:00
MONITORING_SMARTPLACE_START_GRACE_MINUTES=15
MONITORING_SMARTPLACE_MAX_DURATION_MINUTES=180
MONITORING_SMARTPLACE_EXPECTED_SCOPES=hanchon:한촌설렁탕,yuksoodang:육수당
```

- [ ] **Step 4: 전체 API 테스트 통과 확인**

Run: `python -m pytest apps/api/tests -q`
Expected: PASS.

- [ ] **Step 5: Task 5 커밋**

```powershell
git add apps/api/src/monitoring_api/adapters/smartplace.py apps/api/src/monitoring_api/config.py apps/api/src/monitoring_api/composition.py apps/api/tests .env.example
git commit -m "feat: add SmartPlace monitoring adapter"
```

### Task 6: 브랜드별 행과 하위 작업 상세 UI

**Files:**
- Modify: `apps/web/src/features/monitoring/components/runs-table.tsx`
- Create: `apps/web/src/features/monitoring/components/runs-table.test.tsx`
- Modify: `apps/web/src/features/monitoring/components/run-detail-sheet.tsx`
- Modify: `apps/web/src/features/monitoring/components/run-detail-sheet.test.tsx`
- Modify: `apps/web/src/features/monitoring/monitoring-page.test.tsx`
- Create: `apps/web/src/features/monitoring/data/format-count.ts`
- Create: `apps/web/src/features/monitoring/data/format-count.test.ts`

**Interfaces:**
- Consumes: Task 4의 scope와 nullable 집계
- Produces: 실행 이력 브랜드 열, 상세 단계 행, 미확인 집계 `-`

- [ ] **Step 1: 브랜드·nullable·제어 부재 실패 테스트 작성**

```typescript
expect(screen.getByRole('cell', { name: '한촌설렁탕' })).toBeInTheDocument()
expect(screen.getAllByText('-').length).toBeGreaterThan(0)
expect(screen.getByRole('cell', { name: 'pos_linked' })).toBeInTheDocument()
expect(screen.queryByRole('button', { name: /실행|재실행|중지/ })).not.toBeInTheDocument()
```

- [ ] **Step 2: UI 테스트가 현재 표시 계약에서 실패하는지 확인**

Run: `npm test -- --run apps/web/src/features/monitoring/components/runs-table.test.tsx apps/web/src/features/monitoring/components/run-detail-sheet.test.tsx apps/web/src/features/monitoring/monitoring-page.test.tsx`
Expected: FAIL on brand or null rendering.

- [ ] **Step 3: 기존 테이블과 상세 패널 최소 확장**

브랜드 열에 `scope_name ?? '-'`를 표시한다. `data/format-count.ts`의
`formatCount(value: number | null): string`은 null이면 `-`, 아니면 ko-KR 숫자를
반환한다. 목록과 상세 패널이 같은 함수를 사용하며 제어 버튼은 추가하지 않는다.

- [ ] **Step 4: 전체 웹 검증 통과 확인**

Run: `npm test -- --run`

Run: `npm run lint`

Run: `npm run typecheck`

Run: `npm run build`

Expected: 모두 PASS.

- [ ] **Step 5: Task 6 커밋**

```powershell
git add apps/web/src/features/monitoring
git commit -m "feat: show SmartPlace brand monitoring"
```

### Task 7: 운영 문서와 비운영 통합 검증

**Files:**
- Modify: `README.md`
- Modify: `docs/운영/로컬-실행.md`
- Modify: `docs/운영/배포-및-장애대응.md`
- Create: `docs/운영/smartplace-사후-모니터링.md`
- Create: `apps/api/tests/test_operations_docs.py`

**Interfaces:**
- Consumes: Tasks 1~6 환경변수, DDL, 읽기 전용 API·UI 계약
- Produces: DBA 적용, 권한 분리, smoke, 롤백 절차

- [ ] **Step 1: 운영 문서 계약 테스트 추가**

```python
for token in (
    "SMARTPLACE_COLLECTION_RUN", "SMARTPLACE_COLLECTION_ATTEMPT",
    "SELECT 전용", "ACCOUNT_PROTECTED", "NOT_RUN", "ABORTED",
    "대시보드에서 실행하지 않는다",
):
    assert token in operations_text
```

- [ ] **Step 2: 새 운영 문서 부재로 실패하는지 확인**

Run: `python -m pytest apps/api/tests -q`
Expected: FAIL only on the new documentation contract test.

- [ ] **Step 3: 배포·검증·롤백 절차 작성**

DDL 사전검토, 최소 권한, 크롤러 계측 배포, API·웹 배포, 첫 예약 실행의 두 브랜드와
세 작업 대조를 순서대로 기록한다. 롤백은 계측과 SmartPlace 어댑터 등록만 이전
릴리스로 되돌리고 감사 테이블과 과거 행은 삭제하지 않는다.

- [ ] **Step 4: 두 저장소 비운영 회귀 검증**

Run in `C:/workspace/naver_crawling`:

```powershell
python -m pytest tests/test_smartplace_monitoring_sql.py tests/test_smartplace_monitoring.py tests/test_smartplace_crawler_v22.py tests/test_smartplace_browser.py tests/test_smartplace_parsers.py -q
```

Run in `C:/workspace/collection-monitoring-platform`:

```powershell
python -m pytest apps/api/tests -q
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: 모두 PASS. 운영 DB, 브라우저, 스케줄러, 이메일은 실행하지 않는다.

- [ ] **Step 5: Task 7 커밋**

```powershell
git add README.md docs/운영
git commit -m "docs: operate SmartPlace post-collection monitoring"
```

## 운영 적용 전 별도 승인 게이트

구현 완료 후에도 naverDB DDL, 서버 배포, 계정 권한, Windows 예약 작업, 실제 예약
회차, 이메일 구현·발송은 각각 별도 승인 없이는 수행하지 않는다.
