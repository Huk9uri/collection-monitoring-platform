import { describe, expect, it } from 'vitest'

import { monitoringQueries } from './queries'

describe('monitoringQueries', () => {
  it('모든 query key를 monitoring·영역·조건 형식으로 만든다', () => {
    const conditions = {
      collectorId: 'fcdaum',
      startedFrom: '2026-09-01T00:00:00Z',
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
      monitoringQueries.runDetail({ collectorId: 'hmr', runId: 'run-1' })
        .queryKey,
    ).toEqual([
      'monitoring',
      'run-detail',
      { collectorId: 'hmr', runId: 'run-1' },
    ])
    expect(
      monitoringQueries.freshness({ collectorId: 'hmr' }).queryKey,
    ).toEqual(['monitoring', 'freshness', { collectorId: 'hmr' }])
  })

  it('자동 polling을 설정하지 않는다', () => {
    const options = [
      monitoringQueries.summary(),
      monitoringQueries.collectors(),
      monitoringQueries.runs({}),
      monitoringQueries.runDetail({ collectorId: 'hmr', runId: 'run-1' }),
      monitoringQueries.freshness({}),
    ]

    expect(options.every((option) => option.refetchInterval === undefined)).toBe(
      true,
    )
  })
})
