# 인증·모니터링 정책 제어 DB 스키마 적용

## 적용 범위

`apps/api/sql/100_create_monitoring_control_tables.sql`은 제어 테이블 7개를
단일 트랜잭션으로 생성한다. SQL Server 2016 이상의 JSON 검사 기능을 사용한다.
기존 테이블이 있으면 실패하고 이번 실행을 롤백한다. 재실행을 위한 자동 삭제나
기존 객체 변경은 하지 않는다. 운영 대상 DB와 스키마는 적용 전에 확정해야 한다.
`dbo` 이외 스키마를 사용하면 두 스크립트의 객체 참조를 함께 변경한다.

## 적용 절차

1. DBA가 대상 DB, 백업 및 변경 절차, 기존 객체 충돌 여부를 확인한다.
2. 승인된 마이그레이션 계정으로 100 스크립트를 실행한다.
3. 런타임 전용 계정에 아래 표의 권한만 부여한다. 스크립트는 계정을 생성하거나
   권한을 자동 부여하지 않는다.
4. 해당 런타임 계정으로 105 스크립트를 실행해 누락 테이블, 컬럼, 제약조건,
   인덱스 및 유효 권한을 검토한다. DBA는 메타데이터 가시성으로 숨겨진 객체도
   포함해 업무 테이블 쓰기 권한 부재를 확인한다.

| 테이블 | 런타임 권한 | 용도 |
| --- | --- | --- |
| monitoring_user | SELECT, UPDATE | 인증 및 본인 비밀번호 변경 |
| monitoring_session | SELECT, INSERT, UPDATE, DELETE | 발급·갱신·폐기·제한된 정리 |
| monitoring_collector_policy | SELECT, INSERT, UPDATE | 최초 정책 및 전체 교체 |
| monitoring_collector_schedule | SELECT, INSERT, DELETE | 일정 목록 교체 |
| monitoring_collector_freshness_policy | SELECT, INSERT, DELETE | SLA 목록 교체 |
| monitoring_policy_history | SELECT, INSERT | 변경 이력 조회·추가 |
| monitoring_auth_audit | SELECT, INSERT | 보안 감사 및 실패 제한 조회 |

최초 사용자 생성 CLI에는 별도 승인된 계정으로 사용자 INSERT 권한을 제공한다.
런타임 계정에는 CREATE·ALTER·DROP, 감사 테이블 UPDATE·DELETE, 수집 업무
테이블 쓰기 권한을 부여하지 않는다. 소유권과 역할 상속을 포함한 유효 권한으로
판단하며 테이블 목록 조회만으로 다른 DB의 권한 부재를 증명할 수는 없다.
기존 수집 DB 연결은 SELECT 전용으로 유지한다.

## 후속 구현 계약

- 모든 DATETIME2 값은 애플리케이션에서 UTC로 저장한다.
- UUID와 시각은 repository에서 명시적으로 전달한다.
- 사용자 정규화, Argon2id 검사, IANA timezone·등록 수집기·데이터셋 검증,
  활성 일정 필수 조건은 API에서 추가 검증한다.
- 최초 정책 생성의 이전 snapshot은 JSON 객체 `{}`로 저장한다.
- 정책 교체와 이력 추가는 하나의 트랜잭션에서 실행하고 rowversion을 비교한다.
- `account_ip_hash`는 정규화 계정명과 신뢰할 수 있는 클라이언트 IP를 결합한
  SHA-256 지문이다. 별도 로그인 운영 설정을 두지 않는다는 사용자 지시에 따라
  비밀키 설정을 추가하지 않았다. 프록시 신뢰 범위는 배포 전에 확정한다.
  감사에는 원문 오류·비밀번호·토큰을 넣지 않는다.
- 이벤트와 결과 코드는 후속 인증 구현에서 허용 목록으로 제한한다.

## 검증 범위

정적 계약 테스트는 산출물 누락과 주요 보안·무결성 계약을 검사한다.
SQL Server에서의 실행 성공, 트랜잭션 롤백, 대소문자 중복·FK·CHECK 위반 거부,
런타임 최소 권한은 실제 배포 환경에서 추가 검증해야 한다.
이번 단계에서는 실제 DB 연결·DDL 실행을 수행하지 않았다.
