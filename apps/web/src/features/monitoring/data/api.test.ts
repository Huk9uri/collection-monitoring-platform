import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '../../../lib/api'
import { getSummary } from './api'

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
})
