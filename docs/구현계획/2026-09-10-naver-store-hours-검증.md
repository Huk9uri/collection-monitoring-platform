# 네이버 영업시간 모니터링 구현·비운영 검증 보고

작성일: 2026-09-10. 작업 범위는 크롤러 계측, 플랫폼 API/웹, fixture 검증과 운영 자료다. 운영 DB·서버·예약 작업은 변경하지 않았다.

## 변경 구조

### 크롤러 저장소

- `scripts/python/naver_store_hours_monitoring.py`: 정제된 브랜드/단계 계약, UUID5, 시간대 변환, 독립 감사 연결과 멱등 저장, 기본 비활성 환경 경계.
- `scripts/python/naver_store_hours_scheduled_run.py`: 실패 격리 시작/중간/종료 관측, preflight-only 구분, 검증된 메모리 snapshot 전달. 비정상 Apply의 검증된 부분 결과는 감사 용도로만 보존.
- `scripts/python/naver_store_hours_chunk_checkpoint.py`: 자식 보고의 확정 `db_applied`, worker ID/시각을 최종 매장 결과에 보존. 구버전 payload 구조 호환 유지.
- `tests/test_naver_store_hours_monitoring.py`: 신규 계측 테스트 28개.
- `scripts/sql/store_hours_monitoring/{01_create,02_verify}.sql`: DBA 검토용 DDL과 권한/카탈로그 SELECT.
- `docs/naver-store-hours-monitoring-runbook.md`: 크롤러 인계 안내.

예약 스크립트 등 기존 미커밋 사용자 수정 위에 필요한 부분만 추가했다. 기존 사용자 파일을 되돌리거나 커밋/배포하지 않았다.

### 플랫폼 저장소

- `apps/api/src/monitoring_api/adapters/naver_store_hours.py`: SELECT-only 어댑터, 정제 JSON/SQL 대조, 주간 정책, 브랜드 신선도.
- `adapters/base.py`: 선택적 공통 메타데이터와 PARTIAL_FAILURE 매핑.
- `adapters/smartplace.py`, `api/monitoring.py`, `services/monitoring.py`: 서버 브랜드 필터와 브랜드별 신선도 보존, 기존 소스 격리 유지.
- `config.py`, `composition.py`, `.env.example`: 선택적 네이버 연결과 실제 설정 확인 후 사용하는 주간 정책.
- `apps/api/tests/test_naver_store_hours_adapter.py`: 어댑터/계약/SQL/HTTP/정책 회귀.
- `apps/web/src/features/monitoring`: API schema, 필터/URL, 표시명·상세·신선도·카드 및 관련 테스트. 네이버는 독립 수집기로 표시한다.
- `README.md`, `docs/구현계획/2026-09-10-naver-store-hours.md`, `docs/운영/naver-store-hours-사후-모니터링.md`.

상태/지표 상세 대응과 배포·첫 회차·롤백 절차는 [운영 문서](../운영/naver-store-hours-사후-모니터링.md)에 통합했다.

## 검증 결과

Python 3.12 임시 가상환경을 `%TEMP%\store-hours-monitoring-venv`에 준비했다. 기존 API `.venv`는 pytest가 없어 사용하지 않았다. 테스트 의존성은 임시 환경에만 설치했다. pytest 8.4.2, tzdata 2026.3을 사용했다.

| 검사 | 결과 |
| --- | --- |
| 영업시간 관련 `tests/test_naver_store_hours_*.py` 전체 | 485 통과, 신규 계측 28 포함 |
| 플랫폼 API | 222 통과 |
| 웹 `npm test`에 해당하는 vitest run | 85 통과, 14파일 |
| `npm run lint` | 통과, 종료 코드 0 |
| `npm run typecheck` | 통과 |
| `npm run build` | 통과, 종료 코드 0 |
| 실제 생산자→API 함수 계약 대조 | 10개 브랜드 레코드 통과: 성공/부분 실패/실패/사전 점검/RUNNING, worker·retry·시각 근거 포함 |
| 코드 리뷰 | 계측 성공 중복 집계·전부 실패 시 commit 표시는 재현 테스트 후 수정. 재검토에서 차단 결함 없음 |

신규 테스트는 상태/품질 분리, 예상/확정/null, 실제 일부 Apply, 전체 실패, 전체 0/안전 0, preflight-only, UTC/DST, UUID 멱등성, 오류 정제, callback 실패 격리, 마커 실패, 최종 재시도·선행 0, readonly SQL/바인딩, 주간 회차/소스 장애, 웹 브랜드 필터·메타데이터를 확인한다. 기존 예약 회귀는 손상/미완료/provenance 불일치 등 기존 안전 검증을 함께 확인한다.

### 검사 중 발견한 환경 제약

- 샌드박스에서 임시 Python 실행이 출력 없이 지연되어 동일한 fixture 검사를 승인된 일반 실행으로 재실행했다.
- 루트에서 API pytest를 실행하면 기존 루트 `.env`의 연결 의도 검증에 걸려 수집 단계에서 중단됐다. 설정을 수정하지 않고 공식 `test:api`와 같은 `apps/api` 디렉터리에서 실행하여 통과했다. 실제 DB 연결을 수행한 결과가 아니다.
- API 테스트 중 Windows 이벤트 루프 socketpair 오류가 한 번 발생했으나 코드 변경 없이 재실행해 통과했다.
- 범위 밖 리뷰/SmartPlace 테스트까지 수집 목록을 탐색했을 때 pandas 의존성이 없어 해당 테스트 수집은 중단됐다. 요청 범위인 영업시간 관련 테스트 전체는 정상 실행했다.
- 웹 빌드의 Zod `@__PURE__` 주석 경고는 번들러가 해당 주석을 제거한다는 의존성 경고이며 빌드 실패가 아니다.

## 수행하지 않은 운영 검증

운영 SQL Server DDL 적용/실제 principal 권한/운영 driver 연결, 배포 artifact smoke, 실제 Windows 예약값, 실제 네이버 수집/업무 DB 반영, 첫 정규 회차 대조와 메일 발송은 수행하지 않았다. DBA용 SQL은 작성만 했다. 정책값과 크롤러 계측은 기본 비활성이므로 운영 담당자의 확인·승인 후 별도 적용해야 한다.

새 계측 이전 실행의 자동 backfill, 과거 실패 worker 원문 복원, 업무 COLLECT_DT 조회·업무값 변경 시각 추정은 제공하지 않는다. 기록 실패 시 관측 누락 가능성, 최종 시도만 보존하는 범위, parent-window 시각 근거와 독립 감사 보존은 운영 문서에 명시했다.
## 계정 설정 후속 반영

사용자가 크롤러 `.env`의 기존 master 계정과 플랫폼 `.env`의 readonly 계정을 사용한다고 확인했다. 크롤러 계측에 `.env` 읽기 및 기존 NAVER_DB_* 재사용을 추가했다. 별도 감사 계정 설정은 선택 사항이고, 지정 시 HOST/USER/PASSWORD 전체를 요구한다. 프로세스 환경 우선순위·기본 비활성·명시적 시간대/설치 ID 요구는 유지한다.

설정 회귀 6개를 추가한 크롤러 관련 전체 테스트는 491개 통과했다. 플랫폼 .env의 SmartPlace/영업시간 연결 문자열 끝에 남은 불필요한 따옴표만 제거했으며 자격증명은 변경하지 않았다. Settings 및 읽기 전용 서비스 조립 검증도 통과했다. 실제 DB 접속/권한 조회/감사 쓰기/계측 활성화는 하지 않았다.