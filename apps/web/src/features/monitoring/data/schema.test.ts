import { describe, expect, it } from 'vitest'

import {
  collectorsResponseSchema,
  collectorRunSchema,
  freshnessResponseSchema,
  monitoringStatusSchema,
  runsResponseSchema,
  summaryResponseSchema,
  utcDateTimeSchema,
} from './schema'

const validRun = {
  collector_id: 'fcdaum',
  run_id: '00000000-0000-4000-8000-000000000001',
  scheduled_date: '2026-09-08',
  started_at: '2026-09-08T01:00:00Z',
  completed_at: '2026-09-08T01:03:00+00:00',
  status: 'SUCCESS',
  successful_units: 2,
  failed_units: 0,
  source_count: 10,
  inserted_count: 4,
  changed_count: 2,
  unchanged_count: 4,
  attempts: [
    {
      unit_id: 'hanchon',
      unit_name: '한촌설렁탕',
      attempt_no: 1,
      started_at: '2026-09-08T01:00:00Z',
      completed_at: '2026-09-08T01:01:00Z',
      outcome: 'SUCCESS',
      raw_status: 'SUCCESS',
      source_count: 5,
      inserted_count: 2,
      changed_count: 1,
      unchanged_count: 2,
      committed: true,
      error_category: null,
    },
  ],
}

const sourceStatus = {
  registered: 2,
  succeeded: 2,
  failed: 0,
  all_sources_unavailable: false,
}

describe('monitoringStatusSchema', () => {
  it('FastAPI가 노출하는 여덟 상태를 모두 허용한다', () => {
    const statuses = [
      'SUCCESS',
      'SUCCESS_EMPTY',
      'WARNING',
      'PARTIAL_FAILED',
      'FAILED',
      'RUNNING',
      'ABORTED',
      'NOT_RUN',
    ]

    expect(statuses.map((status) => monitoringStatusSchema.parse(status))).toEqual(
      statuses,
    )
  })

  it('공개 계약에 없는 상태를 거부한다', () => {
    expect(monitoringStatusSchema.safeParse('PARTIAL').success).toBe(false)
  })
})

describe('utcDateTimeSchema', () => {
  it('Z와 +00:00 형식의 UTC ISO 8601 시각을 허용한다', () => {
    expect(utcDateTimeSchema.parse('2026-09-08T01:00:00Z')).toBe(
      '2026-09-08T01:00:00Z',
    )
    expect(utcDateTimeSchema.parse('2026-09-08T01:00:00+00:00')).toBe(
      '2026-09-08T01:00:00+00:00',
    )
  })

  it('UTC가 아닌 오프셋과 timezone이 없는 시각을 거부한다', () => {
    expect(utcDateTimeSchema.safeParse('2026-09-08T10:00:00+09:00').success).toBe(
      false,
    )
    expect(utcDateTimeSchema.safeParse('2026-09-08T01:00:00').success).toBe(false)
  })
})

describe('FastAPI 응답 계약', () => {
  it('실행 ID를 실제 uniqueidentifier 계약과 같은 UUID로 제한한다', () => {
    expect(collectorRunSchema.safeParse(validRun).success).toBe(true)
    expect(
      collectorRunSchema.safeParse({ ...validRun, run_id: 'run-20260908' })
        .success,
    ).toBe(false)
  })

  it('하위 시도에 canonical outcome과 원시 상태를 함께 요구한다', () => {
    const attemptWithoutOutcome = { ...validRun.attempts[0] }
    Reflect.deleteProperty(attemptWithoutOutcome, 'outcome')
    const withoutOutcome = {
      ...validRun,
      attempts: [attemptWithoutOutcome],
    }

    expect(collectorRunSchema.safeParse(withoutOutcome).success).toBe(false)
    expect(collectorRunSchema.parse(validRun).attempts[0]).toMatchObject({
      outcome: 'SUCCESS',
      raw_status: 'SUCCESS',
    })
  })

  it('실행 페이지의 중첩 시도와 전체 건수를 검증한다', () => {
    const result = runsResponseSchema.parse({
      items: [validRun],
      errors: [],
      source_status: sourceStatus,
      total: 1,
    })

    expect(result.items[0]?.attempts[0]?.committed).toBe(true)
    expect(result.total).toBe(1)
  })

  it('실행 응답 내 UTC가 아닌 시각을 거부한다', () => {
    expect(
      collectorRunSchema.safeParse({
        ...validRun,
        started_at: '2026-09-08T10:00:00+09:00',
      }).success,
    ).toBe(false)
  })

  it('신선도의 null 최신 시각과 구조화된 소스 오류를 허용한다', () => {
    const result = freshnessResponseSchema.parse({
      items: [
        {
          collector_id: 'hmr',
          dataset_id: 'orders',
          last_successful_check_at: '2026-09-08T01:00:00Z',
          latest_data_at: null,
          freshness_sla_minutes: 180,
          freshness_overdue: true,
        },
      ],
      errors: [
        {
          collector_id: 'fcdaum',
          code: 'SOURCE_UNAVAILABLE',
          message: '데이터 소스를 조회할 수 없습니다.',
        },
      ],
      source_status: {
        registered: 2,
        succeeded: 1,
        failed: 1,
        all_sources_unavailable: false,
      },
    })

    expect(result.items[0]?.latest_data_at).toBeNull()
    expect(result.items[0]?.last_successful_check_at).toBe(
      '2026-09-08T01:00:00Z',
    )
    expect(result.items[0]?.freshness_overdue).toBe(true)
    expect(result.errors[0]?.code).toBe('SOURCE_UNAVAILABLE')
  })

  it('수집기 요약은 미실행 수집기와 신선도 상태를 실행 이력 없이 표현한다', () => {
    const result = collectorsResponseSchema.parse({
      items: [
        {
          collector_id: 'hmr',
          display_name: 'HMR',
          status: 'NOT_RUN',
          latest_run: null,
          schedule_timezone: 'Asia/Seoul',
          daily_scheduled_time: '03:00:00',
          max_duration_minutes: 120,
          last_successful_check_at: null,
          latest_data_at: null,
          freshness_overdue: false,
          freshness: [
            {
              collector_id: 'hmr',
              dataset_id: 'orders',
              last_successful_check_at: null,
              latest_data_at: null,
              freshness_sla_minutes: 180,
              freshness_overdue: false,
            },
          ],
        },
      ],
      errors: [],
      source_status: sourceStatus,
    })

    expect(result.items[0]).toMatchObject({
      collector_id: 'hmr',
      status: 'NOT_RUN',
      latest_run: null,
      freshness: [
        expect.objectContaining({
          collector_id: 'hmr',
          dataset_id: 'orders',
        }),
      ],
    })
  })

  it('summary는 오늘 실행 건수와 소스 가용성을 별도 객체로 검증한다', () => {
    const result = summaryResponseSchema.parse({
      overall_status: 'PARTIAL_FAILED',
      registered_collectors: 2,
      today_success_runs: 3,
      today_incident_runs: 1,
      running_runs: 0,
      errors: [],
      source_status: sourceStatus,
    })

    expect(result).toMatchObject({
      overall_status: 'PARTIAL_FAILED',
      registered_collectors: 2,
      today_success_runs: 3,
      today_incident_runs: 1,
      running_runs: 0,
    })
  })

  it('응답이 source_status를 누락하면 소스 장애 수준을 판정할 수 없어 거부한다', () => {
    expect(
      runsResponseSchema.safeParse({ items: [], errors: [], total: 0 }).success,
    ).toBe(false)
  })
})
