import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CollectorRun } from '../data/schema'
import { RunDetailSheet } from './run-detail-sheet'

afterEach(cleanup)

const partialFailedRun: CollectorRun = {
  collector_id: 'fcdaum',
  run_id: 'run-20260908',
  scheduled_date: '2026-09-08',
  started_at: '2026-09-08T01:00:00Z',
  completed_at: '2026-09-08T01:03:00Z',
  status: 'PARTIAL_FAILED',
  successful_units: 1,
  failed_units: 1,
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
    {
      unit_id: 'yuksudang',
      unit_name: '육수당',
      attempt_no: 2,
      started_at: '2026-09-08T01:02:00Z',
      completed_at: '2026-09-08T01:03:00Z',
      raw_status: 'FAILED',
      source_count: 5,
      inserted_count: 0,
      changed_count: 0,
      unchanged_count: 0,
      committed: false,
      error_category: 'DB_WRITE_FAILED',
    },
  ],
}

describe('RunDetailSheet', () => {
  it('부분 실패를 장애로 표시하고 성공·실패 하위 작업을 구분한다', () => {
    render(
      <RunDetailSheet
        open
        onOpenChange={vi.fn()}
        run={partialFailedRun}
        isLoading={false}
      />,
    )

    expect(screen.getByRole('dialog', { name: '실행 상세' })).toBeTruthy()
    expect(screen.getByText('부분 실패').dataset.severity).toBe('incident')
    expect(screen.getByText('한촌설렁탕').closest('tr')?.textContent).toContain(
      '성공',
    )
    expect(screen.getByText('육수당').closest('tr')?.textContent).toContain('실패')
    expect(screen.getByText('육수당').closest('tr')?.textContent).toContain(
      'DB_WRITE_FAILED',
    )
  })
})
