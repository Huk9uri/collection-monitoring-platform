import { describe, expect, it } from 'vitest'

import {
  collectorRunSchema,
  freshnessResponseSchema,
  monitoringStatusSchema,
  runsResponseSchema,
  utcDateTimeSchema,
} from './schema'

const validRun = {
  collector_id: 'fcdaum',
  run_id: 'run-20260908',
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
  it('실행 페이지의 중첩 시도와 전체 건수를 검증한다', () => {
    const result = runsResponseSchema.parse({
      items: [validRun],
      errors: [],
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
          latest_at: null,
        },
      ],
      errors: [
        {
          collector_id: 'fcdaum',
          code: 'SOURCE_UNAVAILABLE',
          message: '데이터 소스를 조회할 수 없습니다.',
        },
      ],
    })

    expect(result.items[0]?.latest_at).toBeNull()
    expect(result.errors[0]?.code).toBe('SOURCE_UNAVAILABLE')
  })
})
