import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '../../../lib/api'
import { getRuns, getSummary, type RunsQueryConditions } from './api'

describe('monitoring API', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('HTTP 응답을 Zod 계약으로 검증한다', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        items: [
          {
            collector_id: 'hmr',
            run_id: 'run-invalid-time',
            scheduled_date: '2026-09-08',
            started_at: '2026-09-08T10:00:00+09:00',
            completed_at: null,
            status: 'SUCCESS',
            successful_units: 1,
            failed_units: 0,
            source_count: 1,
            inserted_count: 1,
            changed_count: 0,
            unchanged_count: 0,
            attempts: [],
          },
        ],
        errors: [],
      },
    })

    await expect(getSummary()).rejects.toMatchObject({ name: 'ZodError' })
  })

  it.each<{
    name: string
    conditions: RunsQueryConditions
  }>([
    { name: 'page size 0', conditions: { pageSize: 0 } },
    { name: 'page size 101', conditions: { pageSize: 101 } },
    { name: '음수 offset', conditions: { offset: -1 } },
    { name: 'offset 10001', conditions: { offset: 10_001 } },
    { name: '소수 offset', conditions: { offset: 1.5 } },
    { name: '소수 page size', conditions: { pageSize: 50.5 } },
    {
      name: 'UTC가 아닌 시작 시각',
      conditions: { startedFrom: '2026-09-08T10:00:00+09:00' },
    },
    {
      name: '93일을 초과한 기간',
      conditions: {
        startedFrom: '2026-06-06T00:00:00Z',
        startedTo: '2026-09-08T00:00:00Z',
      },
    },
    {
      name: '시작보다 빠른 종료 시각',
      conditions: {
        startedFrom: '2026-09-08T00:00:00Z',
        startedTo: '2026-09-07T23:59:59Z',
      },
    },
    {
      name: 'canonical enum이 아닌 상태',
      conditions: { status: 'PARTIAL' } as unknown as RunsQueryConditions,
    },
  ])('$name 조건은 HTTP 요청 전에 거부한다', async ({ conditions }) => {
    const request = vi.spyOn(apiClient, 'get')

    await expect(getRuns(conditions)).rejects.toMatchObject({ name: 'ZodError' })
    expect(request).not.toHaveBeenCalled()
  })

  it('93일 경계 조건을 FastAPI query parameter로 변환한다', async () => {
    const request = vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: { items: [], errors: [], total: 0 },
    })

    await getRuns({
      collectorId: 'fcdaum',
      startedFrom: '2026-06-07T00:00:00Z',
      startedTo: '2026-09-08T00:00:00Z',
      status: 'PARTIAL_FAILED',
      offset: 10_000,
      pageSize: 100,
    })

    expect(request).toHaveBeenCalledWith('/api/v1/monitoring/runs', {
      params: {
        collector_id: 'fcdaum',
        started_from: '2026-06-07T00:00:00Z',
        started_to: '2026-09-08T00:00:00Z',
        status: 'PARTIAL_FAILED',
        offset: 10_000,
        page_size: 100,
      },
    })
  })
})
