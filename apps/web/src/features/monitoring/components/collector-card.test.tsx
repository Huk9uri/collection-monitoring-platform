import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { CollectorSummary } from '../data/schema'
import { CollectorCard } from './collector-card'

afterEach(cleanup)

const summaryWithUnknownCounts: CollectorSummary = {
  collector_id: 'smartplace',
  display_name: 'SmartPlace',
  status: 'FAILED',
  latest_run: {
    collector_id: 'smartplace',
    run_id: '00000000-0000-4000-8000-000000000001',
    scheduled_date: '2026-09-09',
    started_at: '2026-09-09T01:00:00Z',
    completed_at: '2026-09-09T01:01:00Z',
    status: 'FAILED',
    successful_units: 0,
    failed_units: 1,
    scope_id: 'hanchon',
    scope_name: '한촌설렁탕',
    source_count: null,
    inserted_count: null,
    changed_count: null,
    unchanged_count: null,
    attempts: [],
  },
  schedule_timezone: 'Asia/Seoul',
  daily_scheduled_time: '04:00:00',
  max_duration_minutes: 180,
  last_successful_check_at: null,
  latest_data_at: null,
  freshness_overdue: false,
  freshness: [],
}

describe('CollectorCard', () => {
  it('미확정 집계를 정상적인 0건으로 표시하지 않는다', () => {
    render(<CollectorCard summary={summaryWithUnknownCounts} />)

    expect(
      screen.getByRole('article', { name: 'SmartPlace 최신 상태' }).textContent,
    ).toContain('신규 / 변경 / 동일- / - / -')
  })
})
