"""환경 정책을 DB 장애 fallback snapshot으로 변환한다."""

from datetime import time

from monitoring_api.control_db import build_control_database
from monitoring_api.repositories.policy import PolicyRepository
from monitoring_api.services.policy import PolicyService, Schedule


_DATASETS = {
    'fcdaum': {'reports', 'issues', 'missions'},
    'hmr': {
        'naver', 'godomall', 'coupang', 'lotteon', 'elevenst', 'ssg',
        'cj_onstyle', 'toss',
    },
    'smartplace': set(),
    'naver-store-hours': {'hanchon', 'yuksoodang'},
    'naver-review-visitor': {'visitor-reviews'},
    'naver-review-blog': {'blog-reviews'},
}


def _daily_review_seed(scheduled_time: time) -> dict:
    """제어 DB에 최초 저장하기 전 설정 화면에 표시할 모니터링 기준이다."""

    return {
        'timezone_name': 'Asia/Seoul',
        'max_duration_minutes': 360,
        'start_grace_minutes': 30,
        'schedule_attribution_window_minutes': 360,
        'schedules': [
            Schedule(
                weekday_number=weekday,
                scheduled_time=scheduled_time,
            ).model_dump(mode='json')
            for weekday in range(1, 8)
        ],
        'monitoring_enabled': True,
        'freshness': {},
    }


_REVIEW_POLICY_SEEDS = {
    'naver-review-visitor': _daily_review_seed(time(7, 0)),
    'naver-review-blog': _daily_review_seed(time(7, 30)),
}


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
    fallback = {}
    for collector_id in collector_ids:
        if collector_id in _REVIEW_POLICY_SEEDS:
            fallback[collector_id] = _REVIEW_POLICY_SEEDS[collector_id]
            continue
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
                         {key: _DATASETS.get(key, set()) for key in collector_ids})
