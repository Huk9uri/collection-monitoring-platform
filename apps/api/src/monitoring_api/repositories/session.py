"""제어 테이블에 한정된 서버 세션·보안 감사 트랜잭션."""

from datetime import datetime, timedelta
from uuid import uuid4

from monitoring_api.control_db import ControlDatabase
from monitoring_api.security import hash_password, verify_password

# 존재하지 않는 사용자도 동일한 비밀번호 검증 비용을 지불한다.
_DUMMY_HASH = hash_password('dummy-' + str(uuid4()))


class SessionRepository:
    def __init__(self, database: ControlDatabase):
        self.database = database

    @staticmethod
    def _audit(cursor, user_id, event, result, fingerprint, now):
        cursor.execute(
            'INSERT INTO dbo.monitoring_auth_audit '
            '(audit_id,user_id,event_code,result_code,account_ip_hash,occurred_at,request_id) '
            'VALUES (?,?,?,?,?,?,?)',
            (str(uuid4()), user_id, event, result, fingerprint, now, str(uuid4())),
        )

    def login(self, username, password, fingerprint, token_hash, csrf_hash, now,
              failure_limit, lock_minutes, idle_hours, absolute_hours):
        with self.database.transaction() as connection:
            cursor = connection.cursor()
            try:
                # 범위 잠금으로 같은 계정/IP의 병렬 시도도 제한한다.
                cursor.execute(
                    'SELECT COUNT(*) FROM dbo.monitoring_auth_audit WITH (UPDLOCK,HOLDLOCK) '
                    "WHERE account_ip_hash=? AND occurred_at>=? AND event_code='LOGIN' AND result_code='FAILED' "
                    "AND occurred_at>COALESCE((SELECT MAX(occurred_at) FROM dbo.monitoring_auth_audit "
                    "WHERE account_ip_hash=? AND event_code='LOGIN' AND result_code='SUCCESS'),CONVERT(datetime2,'19000101'))",
                    (fingerprint, now - timedelta(minutes=lock_minutes), fingerprint),
                )
                blocked = cursor.fetchone()[0] >= failure_limit
                cursor.execute(
                    'SELECT user_id,username,password_hash,role,is_active FROM dbo.monitoring_user WITH (UPDLOCK,HOLDLOCK) WHERE username=?',
                    (username.strip().lower(),),
                )
                row = cursor.fetchone()
                valid = verify_password(row[2] if row else _DUMMY_HASH, password)
                if blocked or not row or not row[4] or not valid:
                    self._audit(cursor, str(row[0]) if row else None, 'LOGIN', 'BLOCKED' if blocked else 'FAILED', fingerprint, now)
                    return None
                user_id = str(row[0])
                cursor.execute(
                    'INSERT INTO dbo.monitoring_session '
                    '(session_id,user_id,token_hash,csrf_token_hash,idle_expires_at,absolute_expires_at,last_seen_at,created_at) '
                    'VALUES (?,?,?,?,?,?,?,?)',
                    (str(uuid4()), user_id, token_hash, csrf_hash,
                     now + timedelta(hours=idle_hours), now + timedelta(hours=absolute_hours), now, now),
                )
                self._audit(cursor, user_id, 'LOGIN', 'SUCCESS', fingerprint, now)
                cursor.execute('DELETE TOP (100) FROM dbo.monitoring_session WHERE idle_expires_at<=? OR revoked_at IS NOT NULL', (now,))
                return {'user_id': user_id, 'username': row[1], 'role': row[3]}
            finally:
                cursor.close()

    def authenticate(self, digest, now, idle_hours):
        with self.database.transaction() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    'SELECT s.session_id,u.user_id,u.username,u.role,s.csrf_token_hash,s.last_seen_at,s.absolute_expires_at '
                    'FROM dbo.monitoring_session s WITH (UPDLOCK) JOIN dbo.monitoring_user u ON u.user_id=s.user_id '
                    'WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.idle_expires_at>? '
                    'AND s.absolute_expires_at>? AND u.is_active=1 AND s.created_at>=u.password_changed_at',
                    (digest, now, now),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                if now - row[5] >= timedelta(minutes=5):
                    cursor.execute('UPDATE dbo.monitoring_session SET last_seen_at=?,idle_expires_at=? WHERE session_id=?',
                                   (now, min(now + timedelta(hours=idle_hours), row[6]), str(row[0])))
                return {'session_id': str(row[0]), 'user_id': str(row[1]), 'username': row[2],
                        'role': row[3], 'csrf_hash': bytes(row[4])}
            finally:
                cursor.close()

    def rotate_csrf(self, session_id, csrf_hash):
        with self.database.transaction() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute('UPDATE dbo.monitoring_session SET csrf_token_hash=? WHERE session_id=? AND revoked_at IS NULL', (csrf_hash, session_id))
            finally:
                cursor.close()

    def logout(self, user, fingerprint, now):
        with self.database.transaction() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute('UPDATE dbo.monitoring_session SET revoked_at=? WHERE session_id=?', (now, user.session_id))
                self._audit(cursor, user.user_id, 'LOGOUT', 'SUCCESS', fingerprint, now)
            finally:
                cursor.close()

    def change_password(self, user, old_password, new_password, fingerprint, now):
        with self.database.transaction() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute('SELECT password_hash FROM dbo.monitoring_user WITH (UPDLOCK,HOLDLOCK) WHERE user_id=? AND is_active=1', (user.user_id,))
                row = cursor.fetchone()
                if not row or not verify_password(row[0], old_password):
                    self._audit(cursor, user.user_id, 'PASSWORD_CHANGE', 'FAILED', fingerprint, now)
                    return False
                cursor.execute('UPDATE dbo.monitoring_user SET password_hash=?,password_changed_at=?,updated_at=? WHERE user_id=?',
                               (hash_password(new_password), now, now, user.user_id))
                cursor.execute('UPDATE dbo.monitoring_session SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL', (now, user.user_id))
                self._audit(cursor, user.user_id, 'PASSWORD_CHANGE', 'SUCCESS', fingerprint, now)
                return True
            finally:
                cursor.close()
