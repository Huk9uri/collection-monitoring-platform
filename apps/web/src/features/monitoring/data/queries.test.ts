import { describe, expect, it } from 'vitest'

import { monitoringQueries } from './queries'

const runId = '11111111-1111-4111-8111-111111111111'

describe('monitoringQueries', () => {
  it('화면 query 집합에는 독립 freshness 요청을 제공하지 않는다', () => {
    expect(monitoringQueries).not.toHaveProperty('freshness')
  })

  it('모든 query key를 monitoring·영역·조건 형식으로 만든다', () => {
    const conditions = {
      collectorId: 'fcdaum',
      startedFrom: '2026-09-01T00:00:00Z',
      status: 'FAILED' as const,
      offset: 50,
      pageSize: 50,
    }

    expect(monitoringQueries.summary().queryKey).toEqual([
      'monitoring',
      'summary',
      {},
    ])
    expect(monitoringQueries.collectors().queryKey).toEqual([
      'monitoring',
      'collectors',
      {},
    ])
    expect(monitoringQueries.runs(conditions).queryKey).toEqual([
      'monitoring',
      'runs',
      conditions,
    ])
    expect(
      monitoringQueries.runDetail({ collectorId: 'hmr', runId }).queryKey,
    ).toEqual([
      'monitoring',
      'run-detail',
      { collectorId: 'hmr', runId },
    ])
  })

  it('사용자가 invalidate하기 전에는 자동 재조회하지 않는다', () => {
    const options = [
      monitoringQueries.summary(),
      monitoringQueries.collectors(),
      monitoringQueries.runs({}),
      monitoringQueries.runDetail({ collectorId: 'hmr', runId }),
    ]

    for (const option of options) {
      expect(option.staleTime).toBe(Number.POSITIVE_INFINITY)
      expect(option.refetchInterval).toBeUndefined()
      expect(option.refetchOnWindowFocus).toBe(false)
      expect(option.refetchOnReconnect).toBe(false)
      expect(option.refetchOnMount).toBe(false)
    }
  })
})
