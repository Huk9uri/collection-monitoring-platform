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
  target_kind: null,
  target_date_from: null,
  target_date_to: null,
  target_place_id: null,
  scheduled_date: '2026-09-08',
  started_at: '2026-09-08T01:00:00Z',
  completed_at: '2026-09-08T01:03:00+00:00',
  status: 'SUCCESS',
  successful_units: 2,
  failed_units: 0,
  scope_id: null,
  scope_name: null,
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
  it.each([0, 10, null])('대상 매장 수 %s를 응답에 보존한다', (target_store_count) => {
    expect(collectorRunSchema.parse({ ...validRun, target_store_count })).toHaveProperty('target_store_count', target_store_count)
  })

  it('대상 매장 수 누락은 기존 수집기와 호환한다', () => {
    expect(collectorRunSchema.safeParse(validRun).success).toBe(true)
  })

  it.each([-1, 1.5])('잘못된 대상 매장 수 %s를 거부한다', (target_store_count) => {
    expect(collectorRunSchema.safeParse({ ...validRun, target_store_count }).success).toBe(false)
  })

  it('정기 슬롯 UTC 시각을 보존하고 기존 누락과 null은 호환한다', () => {
    expect(collectorRunSchema.parse({ ...validRun, scheduled_at: '2026-09-07T22:00:00Z' })).toHaveProperty('scheduled_at', '2026-09-07T22:00:00Z')
    expect(collectorRunSchema.parse({ ...validRun, scheduled_at: null })).toHaveProperty('scheduled_at', null)
    expect(collectorRunSchema.safeParse(validRun).success).toBe(true)
  })

  it.each(['2026-09-08T07:00:00+09:00', '2026-09-07T22:00:00'])('정기 슬롯의 비 UTC 시각 %s를 거부한다', (scheduled_at) => {
    expect(collectorRunSchema.safeParse({ ...validRun, scheduled_at }).success).toBe(false)
  })

  it.each(['scheduled', 'manual', 'backfill'] as const)(
    '실행 종류 %s를 허용한다',
    (kind) => {
      expect(
        collectorRunSchema.parse({ ...validRun, execution_kind: kind })
          .execution_kind,
      ).toBe(kind)
    },
  )

  it('기간 대상은 시작일과 종료일이 모두 있고 순서가 맞아야 한다', () => {
    expect(
      collectorRunSchema.safeParse({
        ...validRun,
        target_kind: 'date-range',
        target_date_from: '2026-02-01',
        target_date_to: null,
      }).success,
    ).toBe(false)
    expect(
      collectorRunSchema.safeParse({
        ...validRun,
        target_kind: 'date-range',
        target_date_from: '2026-02-02',
        target_date_to: '2026-02-01',
      }).success,
    ).toBe(false)
  })

  it('단일 매장은 비어 있지 않은 place ID만 허용한다', () => {
    expect(
      collectorRunSchema.safeParse({
        ...validRun,
        target_kind: 'single-store',
        target_place_id: ' ',
      }).success,
    ).toBe(false)
  })

  it('전체 매장은 대상 ID와 날짜를 허용하지 않는다', () => {
    expect(
      collectorRunSchema.safeParse({
        ...validRun,
        target_kind: 'all-stores',
        target_place_id: '123456',
      }).success,
    ).toBe(false)
  })

  it('기존 수집기의 대상 메타데이터 누락을 허용한다', () => {
    const legacyRun = { ...validRun }
    Reflect.deleteProperty(legacyRun, 'target_kind')
    Reflect.deleteProperty(legacyRun, 'target_date_from')
    Reflect.deleteProperty(legacyRun, 'target_date_to')
    Reflect.deleteProperty(legacyRun, 'target_place_id')

    expect(collectorRunSchema.parse(legacyRun).target_kind).toBeUndefined()
  })

  it('실행 ID를 실제 uniqueidentifier 계약과 같은 UUID로 제한한다', () => {
    expect(collectorRunSchema.safeParse(validRun).success).toBe(true)
    expect(
      collectorRunSchema.safeParse({ ...validRun, run_id: 'run-20260908' })
        .success,
    ).toBe(false)
  })

  it('브랜드 범위와 실패 전 미확정 집계를 보존한다', () => {
    const smartplaceRun = {
      ...validRun,
      collector_id: 'smartplace',
      scope_id: 'hanchon',
      scope_name: '한촌설렁탕',
      source_count: null,
      inserted_count: null,
      changed_count: null,
      unchanged_count: null,
      attempts: [
        {
          ...validRun.attempts[0],
          source_count: null,
          inserted_count: null,
          changed_count: null,
          unchanged_count: null,
        },
      ],
    }

    expect(collectorRunSchema.parse(smartplaceRun)).toMatchObject({
      scope_id: 'hanchon',
      scope_name: '한촌설렁탕',
      source_count: null,
      inserted_count: null,
      changed_count: null,
      unchanged_count: null,
    })
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

it('네이버 실행의 확장 메타데이터를 보존하고 잘못된 집계를 거부한다', () => {
  const extension = { parent_run_id: validRun.run_id, raw_status: 'SUCCESS', execution_kind: 'preflight-only', review_count: 2, failure_count: 0, applied_count: null, coverage_count: null, committed: false, successful_check_at: null, error_category: null }
  expect(collectorRunSchema.parse({ ...validRun, ...extension })).toMatchObject(extension)
  expect(collectorRunSchema.safeParse({ ...validRun, review_count: -1 }).success).toBe(false)
  expect(collectorRunSchema.safeParse({ ...validRun, successful_check_at: '2026-09-08T10:00:00+09:00' }).success).toBe(false)
  const attempt = { ...validRun.attempts[0], child_run_id: validRun.run_id, stage: 'dry-run', store_codes: ['001'] }
  expect(collectorRunSchema.parse({ ...validRun, attempts: [attempt] }).attempts[0]).toMatchObject(attempt)
})

it('하위 시각의 증거 종류를 보존하고 계약 외 값을 거부한다', () => {
  const attempt = { ...validRun.attempts[0], timing_basis: 'parent-window' }
  expect(collectorRunSchema.parse({ ...validRun, attempts: [attempt] }).attempts[0]).toMatchObject({ timing_basis: 'parent-window' })
  expect(collectorRunSchema.safeParse({ ...validRun, attempts: [{ ...attempt, timing_basis: 'estimated' }] }).success).toBe(false)
})

it.each(['fcdaum', 'hmr', 'smartplace'])('기존 %s API의 null 시도 메타데이터를 현황과 이력에서 허용한다', (collectorId) => {
  const run = {
    ...validRun,
    collector_id: collectorId,
    attempts: validRun.attempts.map((attempt) => ({
      ...attempt, store_codes: null, child_run_id: null, stage: null, timing_basis: null,
    })),
  }
  const history = runsResponseSchema.safeParse({ items: [run], errors: [], source_status: sourceStatus, total: 1 })
  expect(history.success).toBe(true)
  const collectors = collectorsResponseSchema.parse({
    items: [{ collector_id: collectorId, display_name: collectorId, status: 'SUCCESS', latest_run: run,
      schedule_timezone: null, daily_scheduled_time: null, max_duration_minutes: null,
      last_successful_check_at: null, latest_data_at: null, freshness_overdue: false, freshness: [] }],
    errors: [], source_status: sourceStatus,
  })
  expect(collectors.items[0].latest_run?.attempts[0].store_codes).toBeNull()
})
