"""정책 전체 교체와 감사 이력의 원자적 저장."""

from datetime import UTC, datetime
import json
from uuid import uuid4

from monitoring_api.services.policy import MonitoringPolicy


class PolicyRepository:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _get(cursor, collector_id, *, lock=False):
        hint = ' WITH (UPDLOCK,HOLDLOCK)' if lock else ''
        cursor.execute('SELECT timezone_name,max_duration_minutes,start_grace_minutes,schedule_attribution_window_minutes,monitoring_enabled,version,updated_at '
                       'FROM dbo.monitoring_collector_policy' + hint + ' WHERE collector_id=?', (collector_id,))
        row = cursor.fetchone()
        if not row:
            return None
        cursor.execute('SELECT weekday_number,scheduled_time,schedule_enabled FROM dbo.monitoring_collector_schedule WHERE collector_id=? ORDER BY weekday_number,scheduled_time', (collector_id,))
        schedules = [{'weekday_number': r[0], 'scheduled_time': r[1], 'schedule_enabled': bool(r[2])} for r in cursor.fetchall()]
        cursor.execute('SELECT dataset_id,freshness_sla_minutes FROM dbo.monitoring_collector_freshness_policy WHERE collector_id=?', (collector_id,))
        freshness = {r[0]: r[1] for r in cursor.fetchall()}
        policy = MonitoringPolicy(timezone_name=row[0], max_duration_minutes=row[1], start_grace_minutes=row[2],
                                  schedule_attribution_window_minutes=row[3], monitoring_enabled=bool(row[4]),
                                  schedules=schedules, freshness=freshness)
        return {'collector_id': collector_id, 'policy': policy.model_dump(mode='json'), 'version': bytes(row[5]).hex(),
                'updated_at': row[6].replace(tzinfo=UTC).isoformat()}

    def get(self, collector_id):
        with self.database.transaction() as connection:
            cursor = connection.cursor()
            try:
                # 부모 잠금을 유지해 세 개의 SELECT가 같은 정책 버전을 읽는다.
                return self._get(cursor, collector_id, lock=True)
            finally:
                cursor.close()

    def save(self, collector_id, update, user_id):
        with self.database.transaction() as connection:
            cursor = connection.cursor()
            try:
                before = self._get(cursor, collector_id, lock=True)
                if (before['version'] if before else None) != update.version:
                    return {'conflict': True, 'latest': before}
                now = datetime.now(UTC).replace(tzinfo=None)
                values = (update.timezone_name, update.max_duration_minutes, update.start_grace_minutes,
                          update.schedule_attribution_window_minutes, update.monitoring_enabled, now, user_id, collector_id)
                if before:
                    cursor.execute('UPDATE dbo.monitoring_collector_policy SET timezone_name=?,max_duration_minutes=?,start_grace_minutes=?,schedule_attribution_window_minutes=?,monitoring_enabled=?,updated_at=?,updated_by=? WHERE collector_id=?', values)
                else:
                    cursor.execute('INSERT INTO dbo.monitoring_collector_policy (timezone_name,max_duration_minutes,start_grace_minutes,schedule_attribution_window_minutes,monitoring_enabled,updated_at,updated_by,collector_id) VALUES (?,?,?,?,?,?,?,?)', values)
                cursor.execute('DELETE FROM dbo.monitoring_collector_schedule WHERE collector_id=?', (collector_id,))
                cursor.execute('DELETE FROM dbo.monitoring_collector_freshness_policy WHERE collector_id=?', (collector_id,))
                for row in update.schedules:
                    cursor.execute('INSERT INTO dbo.monitoring_collector_schedule (schedule_id,collector_id,weekday_number,scheduled_time,schedule_enabled) VALUES (?,?,?,?,?)',
                                   (str(uuid4()), collector_id, row.weekday_number, row.scheduled_time, row.schedule_enabled))
                for dataset_id, minutes in update.freshness.items():
                    cursor.execute('INSERT INTO dbo.monitoring_collector_freshness_policy (collector_id,dataset_id,freshness_sla_minutes) VALUES (?,?,?)', (collector_id, dataset_id, minutes))
                after = self._get(cursor, collector_id)
                cursor.execute('INSERT INTO dbo.monitoring_policy_history (history_id,collector_id,changed_by,change_reason,before_snapshot,after_snapshot,changed_at,request_id) VALUES (?,?,?,?,?,?,?,?)',
                               (str(uuid4()), collector_id, user_id, update.change_reason, json.dumps(before['policy'] if before else {}),
                                json.dumps(after['policy']), now, str(uuid4())))
                return {'conflict': False, 'latest': after}
            finally:
                cursor.close()

    def history(self, offset=0):
        with self.database.transaction() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute('SELECT history_id,collector_id,changed_by,change_reason,before_snapshot,after_snapshot,changed_at FROM dbo.monitoring_policy_history ORDER BY changed_at DESC,history_id DESC OFFSET ? ROWS FETCH NEXT 50 ROWS ONLY', (offset,))
                return [{'history_id': str(r[0]), 'collector_id': r[1], 'changed_by': str(r[2]), 'change_reason': r[3],
                         'before': json.loads(r[4]), 'after': json.loads(r[5]), 'changed_at': r[6].replace(tzinfo=UTC).isoformat()} for r in cursor.fetchall()]
            finally:
                cursor.close()
