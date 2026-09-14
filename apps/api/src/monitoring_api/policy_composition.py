"""환경 정책을 DB 장애 fallback snapshot으로 변환한다."""

from monitoring_api.control_db import build_control_database
from monitoring_api.repositories.policy import PolicyRepository
from monitoring_api.services.policy import PolicyService, Schedule


class ConfiguredPolicyRepository:
    def __init__(self, settings):
        self.settings = settings

    def get(self, collector_id):
        return PolicyRepository(build_control_database(self.settings)).get(collector_id)

    def save(self, collector_id, update, user_id):
        return PolicyRepository(build_control_database(self.settings)).save(collector_id, update, user_id)

    def history(self, offset=0):
        return PolicyRepository(build_control_database(self.settings)).history(offset)


def build_policy_service(settings, collector_ids):
    datasets = {'fcdaum': {'reports', 'issues', 'missions'},
                'hmr': {'naver', 'godomall', 'coupang', 'lotteon', 'elevenst', 'ssg', 'cj_onstyle', 'toss'},
                'smartplace': set(), 'naver-store-hours': {'hanchon', 'yuksoodang'}}
    fallback = {}
    for collector_id in collector_ids:
        prefix = collector_id.replace('-', '_')
        zone = getattr(settings, f'{prefix}_schedule_timezone', None)
        at = getattr(settings, f'{prefix}_daily_scheduled_time', None)
        days = range(1, 8)
        if collector_id == 'naver-store-hours':
            at = settings.naver_store_hours_weekly_scheduled_time
            day = settings.naver_store_hours_weekly_scheduled_day
            days = [day + 1] if day is not None else []
        freshness = getattr(settings, f'{prefix}_freshness_sla_minutes', {})
        duration = getattr(settings, f'{prefix}_max_duration_minutes', None)
        if (zone and at) or freshness or duration:
            fallback[collector_id] = dict(
                timezone_name=zone, max_duration_minutes=duration,
                start_grace_minutes=getattr(settings, f'{prefix}_start_grace_minutes', None),
                schedule_attribution_window_minutes=getattr(settings, f'{prefix}_schedule_attribution_window_minutes', None),
                schedules=[Schedule(weekday_number=day, scheduled_time=at).model_dump(mode='json') for day in days] if at else [],
                monitoring_enabled=bool(zone and at),
                freshness=freshness,
            )
    return PolicyService(ConfiguredPolicyRepository(settings), fallback,
                         {key: datasets.get(key, set()) for key in collector_ids})
