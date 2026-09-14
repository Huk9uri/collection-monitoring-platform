-- DBA 전용: 대상 데이터베이스와 dbo 스키마를 확인한 뒤 한 번 적용한다.
-- 기존 객체가 있으면 실패하며 전체 트랜잭션을 되돌린다. 권한은 별도로 부여한다.
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    CREATE TABLE dbo.monitoring_user (
        user_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_monitoring_user PRIMARY KEY,
        username NVARCHAR(100) COLLATE Latin1_General_100_CI_AS NOT NULL,
        password_hash NVARCHAR(500) NOT NULL,
        role VARCHAR(30) NOT NULL,
        is_active BIT NOT NULL,
        password_changed_at DATETIME2 NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        version ROWVERSION,
        CONSTRAINT UQ_monitoring_user_username UNIQUE (username),
        CONSTRAINT CK_monitoring_user_username CHECK (LEN(LTRIM(RTRIM(username))) > 0),
        CONSTRAINT CK_monitoring_user_role CHECK (role IN ('viewer', 'admin'))
    );

    CREATE TABLE dbo.monitoring_session (
        session_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_monitoring_session PRIMARY KEY,
        user_id UNIQUEIDENTIFIER NOT NULL,
        token_hash BINARY(32) NOT NULL,
        csrf_token_hash BINARY(32) NOT NULL,
        idle_expires_at DATETIME2 NOT NULL,
        absolute_expires_at DATETIME2 NOT NULL,
        last_seen_at DATETIME2 NOT NULL,
        revoked_at DATETIME2 NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT FK_monitoring_session_user FOREIGN KEY (user_id) REFERENCES dbo.monitoring_user(user_id),
        CONSTRAINT UQ_monitoring_session_token UNIQUE (token_hash),
        CONSTRAINT CK_monitoring_session_expiry CHECK (
            absolute_expires_at >= idle_expires_at AND idle_expires_at >= last_seen_at
            AND last_seen_at >= created_at)
    );
    CREATE INDEX IX_monitoring_session_user ON dbo.monitoring_session(user_id, revoked_at);
    CREATE INDEX IX_monitoring_session_expiry ON dbo.monitoring_session(idle_expires_at);

    CREATE TABLE dbo.monitoring_collector_policy (
        collector_id VARCHAR(50) NOT NULL CONSTRAINT PK_monitoring_collector_policy PRIMARY KEY,
        timezone_name VARCHAR(100) NOT NULL,
        max_duration_minutes INT NULL,
        start_grace_minutes INT NOT NULL,
        schedule_attribution_window_minutes INT NOT NULL,
        monitoring_enabled BIT NOT NULL,
        updated_at DATETIME2 NOT NULL,
        updated_by UNIQUEIDENTIFIER NOT NULL,
        version ROWVERSION,
        CONSTRAINT FK_monitoring_policy_user FOREIGN KEY (updated_by) REFERENCES dbo.monitoring_user(user_id),
        CONSTRAINT CK_monitoring_policy_duration CHECK (max_duration_minutes IS NULL OR max_duration_minutes > 0),
        CONSTRAINT CK_monitoring_policy_grace CHECK (start_grace_minutes > 0),
        CONSTRAINT CK_monitoring_policy_window CHECK (schedule_attribution_window_minutes > 0),
        CONSTRAINT CK_monitoring_policy_timezone CHECK (LEN(LTRIM(RTRIM(timezone_name))) > 0)
    );

    CREATE TABLE dbo.monitoring_collector_schedule (
        schedule_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_monitoring_collector_schedule PRIMARY KEY,
        collector_id VARCHAR(50) NOT NULL,
        weekday_number TINYINT NOT NULL,
        scheduled_time TIME(0) NOT NULL,
        schedule_enabled BIT NOT NULL,
        CONSTRAINT FK_monitoring_schedule_policy FOREIGN KEY (collector_id) REFERENCES dbo.monitoring_collector_policy(collector_id),
        CONSTRAINT CK_monitoring_schedule_weekday CHECK (weekday_number BETWEEN 1 AND 7),
        CONSTRAINT UQ_monitoring_schedule_slot UNIQUE (collector_id, weekday_number, scheduled_time)
    );

    CREATE TABLE dbo.monitoring_collector_freshness_policy (
        collector_id VARCHAR(50) NOT NULL,
        dataset_id VARCHAR(100) NOT NULL,
        freshness_sla_minutes INT NOT NULL,
        CONSTRAINT PK_monitoring_collector_freshness_policy PRIMARY KEY (collector_id, dataset_id),
        CONSTRAINT FK_monitoring_freshness_policy FOREIGN KEY (collector_id) REFERENCES dbo.monitoring_collector_policy(collector_id),
        CONSTRAINT CK_monitoring_freshness_sla CHECK (freshness_sla_minutes > 0)
    );

    CREATE TABLE dbo.monitoring_policy_history (
        history_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_monitoring_policy_history PRIMARY KEY,
        collector_id VARCHAR(50) NOT NULL,
        changed_by UNIQUEIDENTIFIER NOT NULL,
        change_reason NVARCHAR(1000) NOT NULL,
        before_snapshot NVARCHAR(MAX) NOT NULL,
        after_snapshot NVARCHAR(MAX) NOT NULL,
        changed_at DATETIME2 NOT NULL,
        request_id VARCHAR(100) NOT NULL,
        CONSTRAINT FK_monitoring_history_user FOREIGN KEY (changed_by) REFERENCES dbo.monitoring_user(user_id),
        CONSTRAINT FK_monitoring_history_policy FOREIGN KEY (collector_id) REFERENCES dbo.monitoring_collector_policy(collector_id),
        CONSTRAINT CK_monitoring_history_reason CHECK (LEN(LTRIM(RTRIM(change_reason))) > 0),
        CONSTRAINT CK_monitoring_history_before CHECK (ISJSON(before_snapshot) = 1),
        CONSTRAINT CK_monitoring_history_after CHECK (ISJSON(after_snapshot) = 1)
    );
    CREATE INDEX IX_monitoring_policy_history_collector ON dbo.monitoring_policy_history(collector_id, changed_at DESC);

    CREATE TABLE dbo.monitoring_auth_audit (
        audit_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_monitoring_auth_audit PRIMARY KEY,
        user_id UNIQUEIDENTIFIER NULL,
        event_code VARCHAR(40) NOT NULL,
        result_code VARCHAR(40) NOT NULL,
        account_ip_hash BINARY(32) NOT NULL,
        occurred_at DATETIME2 NOT NULL,
        request_id VARCHAR(100) NOT NULL,
        CONSTRAINT FK_monitoring_auth_audit_user FOREIGN KEY (user_id) REFERENCES dbo.monitoring_user(user_id)
    );
    CREATE INDEX IX_monitoring_auth_audit_throttle ON dbo.monitoring_auth_audit(account_ip_hash, occurred_at DESC)
        INCLUDE (event_code, result_code);

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
