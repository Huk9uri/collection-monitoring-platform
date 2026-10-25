# 네이버 리뷰 사후 모니터링 운영

## 1. 목적과 변경 금지 경계

이 기능은 네이버 방문자 리뷰와 블로그 리뷰 수집기가 `naverDB`에 남긴 감사 RUN·ATTEMPT와 업무 데이터의 날짜를 **조회 전용**으로 표시한다. 대상 수집기와 초기 모니터링 기준은 다음과 같다.

| 수집기 | 화면 표시 | KST 정기 슬롯 | 시작 유예 | 최대 실행 | 슬롯 귀속 범위 |
| --- | --- | --- | ---: | ---: | ---: |
| `naver-review-visitor` | 네이버 방문자 리뷰 | 매일 07:00 | 30분 | 360분 | 360분 |
| `naver-review-blog` | 네이버 블로그 리뷰 | 매일 07:30 | 30분 | 360분 | 360분 |

시간대는 모두 `Asia/Seoul`이다. 위 값은 설정 화면에 처음 표시되는 모니터링 정책 기준이며, 실제 Windows Task Scheduler의 예약을 생성하거나 변경하지 않는다. 설정 화면에서 정책을 저장·활성화하기 전에는 해당 기준으로 상태를 확정하지 않는다.

대시보드와 Monitoring API는 크롤러 실행·재실행·중지, Task Scheduler 변경, 운영 DB DML·DDL, 자격 증명·브라우저 프로필·원문 오류의 조회 또는 저장을 수행하지 않는다. API는 별도 SELECT 전용 계정으로만 `naverDB`를 조회한다.

## 2. 적용 전 승인 게이트

다음은 별도 승인 항목이며 이번 구현에서 수행하지 않았다.

1. DBA 권한으로 감사 DDL 적용과 백업·복구 계획 승인
2. 크롤러 기록 권한과 Monitoring API SELECT 전용 권한 승인
3. Monitoring API·웹 배포 및 비밀 저장소의 연결 문자열 주입
4. 서버의 크롤러와 BAT 교체
5. Windows Task Scheduler의 실제 작업·시간·환경변수 확인 또는 변경
6. 감독된 수동 실행과 다음 정기 회차의 운영 검증
7. 설정 화면에서 두 정책 저장 및 활성화

## 3. DDL과 권한 사전검토

수집기 저장소의 SQL은 `C:\workspace\naver_crawling\scripts\sql\review_monitoring\01_create.sql` 및 `02_verify.sql`이다.

1. DBA는 `01_create.sql`의 대상 DB 방어문이 `DB_NAME() = N'naverDB'`인지, RUN·ATTEMPT 테이블과 제약조건을 검토한다.
2. 승인된 계정으로만 `01_create.sql`을 적용한다. 적용 중에는 크롤러와 예약 작업을 실행하지 않는다.
3. `02_verify.sql`을 실행해 테이블·열·제약조건·인덱스 및 최근 RUN을 읽기 전용으로 확인한다.
4. 결과가 계약과 다르면 이후 배포를 중단하고 DBA가 조사한다. 장애 대응을 위해 DDL을 임의 재실행하지 않는다.

크롤러의 `.env`에서 사용하는 `NAVER_DB_NAME`과 `MONITORING_NAVER_REVIEW_CONNECTION_STRING`의 `Database`는 같은 `naverDB`를 가리켜야 한다. API 연결 문자열에는 `ApplicationIntent=ReadOnly`를 포함하고, 실제 권한도 SELECT만 허용한다.

## 4. 배포 순서

1. DDL 적용과 `02_verify.sql` 검증을 마친다.
2. Monitoring API는 네이버 리뷰 연결을 아직 활성화하지 않은 상태로 배포하고, 기존 수집기 health와 조회가 유지되는지 확인한다.
3. 비밀 저장소에 `MONITORING_NAVER_REVIEW_CONNECTION_STRING`을 주입하고 API를 재배포한다. `/health/live`, `/health/ready`, collectors, runs 순서로 SELECT 전용 smoke를 수행한다.
4. 승인된 서버 절차로 크롤러 Python·BAT를 교체한다. `.env`, 로그, 브라우저 프로필, 수집 원문, 캐시를 배포물에 포함하지 않는다.
5. 실제 Task Scheduler의 기존 작업이 방문자 07:00, 블로그 07:30 KST 슬롯과 일치하는지 확인한다. 이 단계에서 스케줄 변경이 필요하면 별도 승인을 받는다.
6. 감독된 수동 실행으로 감사 RUN·ATTEMPT와 업무 적재를 대조한다. 수동·단일 매장·기간 백필 실행은 이력과 상세에는 남지만, 정기 운영 상태/KPI/신선도 판정에는 사용되지 않는다.
7. 설정 화면에서 두 초기 정책을 검토하여 저장·활성화한다. 정책 저장은 실제 Task Scheduler 변경이 아니다.
8. 다음 정기 실행 후 카드·KPI·이력·상세·신선도를 확인한다.

## 5. 정기 슬롯과 상태 판정

정기 실행은 스케줄러가 선언한 KST 슬롯을 `--scheduled-at`으로 전달해야 한다. RUN의 `ScheduledAt`에는 그 슬롯을 UTC로 정규화해 저장하며, 실제 프로세스 시작 시각을 대신 사용하지 않는다. 예를 들어 지연 시작한 07:00 실행은 08:00 회차를 충족하지 않는다.

- 슬롯이 없거나 잘못된 시간대인 실행은 정기 실행으로 취급하지 않는다.
- 정책이 활성화된 뒤 예정 시각과 시작 유예가 지나도 해당 슬롯의 RUN이 없으면 API가 읽기 시점에 `NOT_RUN`을 표시한다.
- `RUNNING`이 최대 실행 시간을 넘으면 API가 읽기 시점에 `ABORTED`를 표시한다.
- 이 표시는 감사 DB 원본 상태를 수정하지 않는다.
- 정책이 비활성화되면 `NOT_RUN`, 시간 초과 `ABORTED`, 정책 기반 신선도 경고를 합성하지 않고 저장된 상태를 유지한다.

정책의 360분 귀속 범위는 정기 RUN과 해당 정책 슬롯을 연결하는 판정 경계다. 실제 작업의 시간 변경 또는 지연 실행을 화면 정책만으로 보정하지 말고, Scheduler 설정과 `ScheduledAt` 선언 값을 함께 조사한다.

## 6. 신선도·이력 확인

신선도는 업무 테이블의 `[date]`가 가진 **날짜 정밀도**만 사용한다. API는 KST 자정을 UTC로 정규화해 표시하므로, 이는 수집 완료 시각이나 행 적재 시각을 뜻하지 않는다. 같은 날짜의 적재 지연·재처리는 감사 RUN의 시작/완료 시각과 ATTEMPT 결과를 별도로 대조한다.

첫 정기 회차 후 다음을 확인한다.

| 점검 대상 | 기대 결과 |
| --- | --- |
| 방문자·블로그 카드 | 선언된 해당 정기 슬롯과 최종 상태를 표시 |
| RUN 이력 | `scheduled`와 수동/백필을 구분해 표시 |
| 상세 ATTEMPT | 매장별 최종 시도, 처리·신규 건수, 반영 여부, 고정 오류 분류만 표시 |
| KPI | 정기 실행만 집계하고 수동·백필은 제외 |
| 신선도 | 업무 날짜와 감사 완료 시각의 정밀도 차이를 고려해 판정 |

`CAPTCHA_DETECTED`, `PAGE_LOAD_FAILED`, `PARSE_FAILED`, `DB_WRITE_FAILED`, `BRAND_MAPPING_FAILED`, `UNEXPECTED_ERROR` 같은 고정 오류 분류만 운영 화면에서 확인한다. 원문 예외, 리뷰 본문, URL, 쿠키, 비밀번호는 기록하거나 노출하지 않는다.

## 7. 롤백과 장애 대응

문제가 있으면 아래 범위로만 롤백한다.

1. 크롤러를 계측 이전 artifact로 되돌린다. 기존 업무 수집 설정과 예약 작업은 변경하지 않는다.
2. Monitoring API에서 네이버 리뷰 어댑터 등록을 제거하거나 직전 artifact로 되돌리고 관련 연결 문자열 주입을 제거한다.
3. 필요하면 웹을 직전 artifact로 되돌린다.
4. 기존 수집기와 API health를 SELECT 전용 smoke로 확인한다.

감사 테이블과 과거 RUN·ATTEMPT는 증거이므로 `DROP`, `DELETE`, `TRUNCATE`, 임의 데이터 보정으로 되돌리지 않는다. DDL 롤백·권한 회수·Task Scheduler 변경은 별도 승인 후 수행한다. 모니터링 기록 누락과 업무 적재 성공이 함께 발생할 수 있으므로, 이 경우 서버 로그의 최소 운영 결과와 업무 테이블 날짜를 승인된 절차로 대조한다.

## 8. 비운영 회귀 검증

운영 DB, 서버, 브라우저, Scheduler를 호출하지 않는 개발 환경에서 아래를 실행한다.

```powershell
# naver_crawling
python -m pytest -q
python -m py_compile scripts/python/naver_review_monitoring.py scripts/python/naver_review_visitor_crawling_v1.4.py scripts/python/naver_review_blog_crawling_v1.4.py

# collection-monitoring-platform
python -m pytest apps/api/tests -q
npm test --workspace @collection-monitoring/web
npm run typecheck --workspace @collection-monitoring/web
npm run lint --workspace @collection-monitoring/web
npm run build --workspace @collection-monitoring/web
```

각 저장소에서 `git diff --check`와 `git status --short`도 확인한다. `.env`, 로그, 리뷰 원문, 브라우저 산출물, 프로필, 캐시가 staged되면 배포와 커밋을 중단한다.
