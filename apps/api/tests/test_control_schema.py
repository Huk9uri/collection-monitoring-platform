"""제어 DB 배포 산출물의 정적 계약 검사. 실제 SQL Server 검증은 별도 수행한다."""

from pathlib import Path
import re

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
TABLES = (
    "monitoring_user", "monitoring_session", "monitoring_collector_policy",
    "monitoring_collector_schedule", "monitoring_collector_freshness_policy",
    "monitoring_policy_history", "monitoring_auth_audit",
)


def test_schema_has_all_control_tables_and_atomic_ddl() -> None:
    sql = (SQL_DIR / "100_create_monitoring_control_tables.sql").read_text(encoding="utf-8")
    for table in TABLES:
        assert f"CREATE TABLE dbo.{table}" in sql
    for contract in ("SET XACT_ABORT ON", "BEGIN TRANSACTION", "COMMIT TRANSACTION", "ROLLBACK TRANSACTION", "THROW"):
        assert contract in sql
    assert "GRANT " not in sql


def test_schema_enforces_security_integrity_and_lookup_indexes() -> None:
    sql = (SQL_DIR / "100_create_monitoring_control_tables.sql").read_text(encoding="utf-8")
    for contract in (
        "token_hash BINARY(32) NOT NULL", "csrf_token_hash BINARY(32) NOT NULL",
        "role IN ('viewer', 'admin')", "COLLATE Latin1_General_100_CI_AS",
        "weekday_number BETWEEN 1 AND 7", "version ROWVERSION",
        "UNIQUE (collector_id, weekday_number, scheduled_time)",
        "ISJSON(before_snapshot)", "ISJSON(after_snapshot)",
        "LEN(LTRIM(RTRIM(change_reason))) > 0", "IX_monitoring_session_user",
        "IX_monitoring_session_expiry", "IX_monitoring_policy_history_collector",
        "IX_monitoring_auth_audit_throttle", "absolute_expires_at >= idle_expires_at",
    ):
        assert contract in sql
    assert not re.search(r"\b(password|token|csrf_token)\s+(?:N?VARCHAR|VARBINARY)", sql, re.I)


def test_verification_is_read_only_and_reports_metadata_and_permissions() -> None:
    sql = (SQL_DIR / "105_verify_monitoring_control_tables.sql").read_text(encoding="utf-8")
    executable = re.sub(r"--[^\n]*", "", sql)
    assert not re.search(r"\b(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|MERGE|EXEC|GRANT|DENY|REVOKE)\b", re.sub(r"'[^']*'", "", executable), re.I)
    for contract in (*TABLES, "sys.columns", "sys.check_constraints", "sys.foreign_keys", "sys.indexes", "HAS_PERMS_BY_NAME"):
        assert contract in sql
