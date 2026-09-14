"""제어 DB 읽기 검증 및 대화형 초기 계정 관리 CLI."""

import argparse
from datetime import UTC, datetime
from getpass import getpass
import os
from uuid import uuid4

from dotenv import dotenv_values

from monitoring_api.config import Settings
from monitoring_api.control_db import build_control_database, ControlDatabaseUnavailable
from monitoring_api.security import hash_password

TABLES = ('monitoring_user', 'monitoring_session', 'monitoring_collector_policy',
          'monitoring_collector_schedule', 'monitoring_collector_freshness_policy',
          'monitoring_policy_history', 'monitoring_auth_audit')


def verify(database):
    with database.transaction() as connection:
        cursor = connection.cursor()
        try:
            for name in TABLES:
                cursor.execute("SELECT OBJECT_ID(?, 'U'), HAS_PERMS_BY_NAME(?, 'OBJECT', 'SELECT')", ('dbo.' + name, 'dbo.' + name))
                row = cursor.fetchone()
                print(f'{name}: exists={bool(row[0])}, select={row[1] == 1}')
            cursor.execute("SELECT HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE TABLE'), HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CONTROL')")
            row = cursor.fetchone()
            print(f'runtime_create_table={row[0] == 1}, runtime_database_control={row[1] == 1}')
        finally:
            cursor.close()


def create_user(database, username, password, role, minimum):
    username = username.strip().lower()
    if not username or len(username) > 100 or not minimum or len(password) < minimum or len(password) > 1024:
        raise ValueError('아이디 또는 비밀번호 정책을 확인하세요.')
    if role not in ('viewer', 'admin'):
        raise ValueError('허용되지 않은 역할입니다.')
    hashed = hash_password(password)
    now = datetime.now(UTC).replace(tzinfo=None)
    with database.transaction() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute('SELECT user_id FROM dbo.monitoring_user WITH (UPDLOCK,HOLDLOCK) WHERE username=?', (username,))
            if cursor.fetchone():
                return False
            user_id = str(uuid4())
            cursor.execute('INSERT INTO dbo.monitoring_user (user_id,username,password_hash,role,is_active,password_changed_at,created_at,updated_at) VALUES (?,?,?,?,1,?,?,?)',
                           (user_id, username, hashed, role, now, now, now))
            cursor.execute('INSERT INTO dbo.monitoring_auth_audit (audit_id,user_id,event_code,result_code,account_ip_hash,occurred_at,request_id) VALUES (?,?,?,?,?,?,?)',
                           (str(uuid4()), user_id, 'USER_CREATED', 'SUCCESS', bytes(32), now, str(uuid4())))
            return True
        finally:
            cursor.close()


def reset_password(database, username, password):
    if not password or len(password) > 1024:
        raise ValueError('비밀번호를 확인하세요.')
    now = datetime.now(UTC).replace(tzinfo=None)
    with database.transaction() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute('SELECT user_id FROM dbo.monitoring_user WITH (UPDLOCK,HOLDLOCK) WHERE username=?', (username.strip().lower(),))
            row = cursor.fetchone()
            if row is None:
                return False
            user_id = str(row[0])
            cursor.execute('UPDATE dbo.monitoring_user SET password_hash=?,password_changed_at=?,updated_at=? WHERE user_id=?', (hash_password(password), now, now, user_id))
            cursor.execute('UPDATE dbo.monitoring_session SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL', (now, user_id))
            cursor.execute('INSERT INTO dbo.monitoring_auth_audit (audit_id,user_id,event_code,result_code,account_ip_hash,occurred_at,request_id) VALUES (?,?,?,?,?,?,?)',
                           (str(uuid4()), user_id, 'PASSWORD_RESET', 'SUCCESS', bytes(32), now, str(uuid4())))
            return True
        finally:
            cursor.close()


def main():
    parser = argparse.ArgumentParser(description='모니터링 제어 DB 운영 도구')
    parser.add_argument('action', choices=['verify', 'create-user', 'reset-password'])
    parser.add_argument('--role', choices=['viewer', 'admin'], default='viewer')
    parser.add_argument('--from-env-once', action='store_true')
    args = parser.parse_args()
    try:
        settings = Settings()
        database = build_control_database(settings)
        if args.action == 'verify':
            verify(database)
            return
        if args.from_env_once:
            if args.action != 'create-user':
                raise ValueError('환경변수 입력은 최초 생성에만 허용합니다.')
            values = {**dotenv_values('.env'), **os.environ}
            username = values.get('MONITORING_ADMIN_USERNAME', '')
            password = values.get('MONITORING_ADMIN_PASSWORD', '')
            role = 'admin'
        else:
            username, password, role = input('아이디: '), getpass('비밀번호: '), args.role
            if password != getpass('비밀번호 확인: '):
                raise ValueError('비밀번호 확인이 일치하지 않습니다.')
        if args.action == 'reset-password':
            updated = reset_password(database, username, password)
            print('비밀번호와 기존 세션을 초기화했습니다.' if updated else '계정을 찾을 수 없습니다.')
        else:
            created = create_user(database, username, password, role, 1)
            print('계정을 생성했습니다.' if created else '동일 계정이 있어 변경하지 않았습니다.')
    except (ControlDatabaseUnavailable, ValueError):
        parser.exit(1, '요청을 완료하지 못했습니다. 연결·권한·입력·운영 정책을 확인하세요.\n')


if __name__ == '__main__':
    main()
