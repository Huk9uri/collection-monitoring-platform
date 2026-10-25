-- 적용 후 런타임 계정으로 실행하는 읽기 전용 점검. 데이터 행과 비밀정보는 조회하지 않는다.
-- missing_table=1이면 누락 또는 메타데이터 가시성 부족이다. DBA가 별도로 확인한다.
SELECT expected.table_name, CASE WHEN t.object_id IS NULL THEN 1 ELSE 0 END AS missing_table
FROM (VALUES ('monitoring_user'), ('monitoring_session'), ('monitoring_collector_policy'),
    ('monitoring_collector_schedule'), ('monitoring_collector_freshness_policy'),
    ('monitoring_policy_history'), ('monitoring_auth_audit')) AS expected(table_name)
LEFT JOIN sys.tables t ON t.name = expected.table_name AND t.schema_id = SCHEMA_ID('dbo');

SELECT t.name AS table_name, c.name AS column_name, ty.name AS type_name,
    c.max_length, c.precision, c.scale, c.is_nullable
FROM sys.tables t JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE t.schema_id = SCHEMA_ID('dbo') AND t.name IN
    ('monitoring_user', 'monitoring_session', 'monitoring_collector_policy',
     'monitoring_collector_schedule', 'monitoring_collector_freshness_policy',
     'monitoring_policy_history', 'monitoring_auth_audit')
ORDER BY t.name, c.column_id;

SELECT OBJECT_NAME(parent_object_id) AS table_name, name, definition, is_disabled, is_not_trusted
FROM sys.check_constraints WHERE parent_object_id IN
    (OBJECT_ID('dbo.monitoring_user'), OBJECT_ID('dbo.monitoring_session'),
     OBJECT_ID('dbo.monitoring_collector_policy'), OBJECT_ID('dbo.monitoring_collector_schedule'),
     OBJECT_ID('dbo.monitoring_collector_freshness_policy'), OBJECT_ID('dbo.monitoring_policy_history'),
     OBJECT_ID('dbo.monitoring_auth_audit'));

SELECT OBJECT_NAME(f.parent_object_id) AS table_name, f.name,
    COL_NAME(fc.parent_object_id, fc.parent_column_id) AS column_name,
    OBJECT_NAME(f.referenced_object_id) AS referenced_table,
    COL_NAME(fc.referenced_object_id, fc.referenced_column_id) AS referenced_column,
    f.is_disabled, f.is_not_trusted
FROM sys.foreign_keys f JOIN sys.foreign_key_columns fc ON fc.constraint_object_id = f.object_id
WHERE f.parent_object_id IN
    (OBJECT_ID('dbo.monitoring_session'), OBJECT_ID('dbo.monitoring_collector_policy'),
     OBJECT_ID('dbo.monitoring_collector_schedule'), OBJECT_ID('dbo.monitoring_collector_freshness_policy'),
     OBJECT_ID('dbo.monitoring_policy_history'), OBJECT_ID('dbo.monitoring_auth_audit'));

SELECT t.name AS table_name, i.name, i.is_unique, i.is_primary_key, i.is_disabled,
    c.name AS column_name, ic.key_ordinal, ic.is_descending_key, ic.is_included_column
FROM sys.tables t JOIN sys.indexes i ON i.object_id = t.object_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE t.schema_id = SCHEMA_ID('dbo') AND t.name IN
    ('monitoring_user', 'monitoring_session', 'monitoring_collector_policy',
     'monitoring_collector_schedule', 'monitoring_collector_freshness_policy',
     'monitoring_policy_history', 'monitoring_auth_audit')
ORDER BY t.name, i.name, ic.index_column_id;

-- 업무 테이블도 포함하여 현재 DB 전체의 유효 권한을 점검한다.
-- 객체가 보이지 않으면 결과에서 누락될 수 있으므로 DBA 목록과 대조한다.
SELECT s.name AS schema_name, t.name AS table_name, p.permission_name,
    HAS_PERMS_BY_NAME(QUOTENAME(s.name) + '.' + QUOTENAME(t.name), 'OBJECT', p.permission_name) AS has_permission
FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
CROSS JOIN (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'), ('ALTER'), ('CONTROL')) p(permission_name);

SELECT p.permission_name, HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', p.permission_name) AS has_permission
FROM (VALUES ('CREATE TABLE'), ('ALTER ANY SCHEMA'), ('CONTROL')) p(permission_name);
