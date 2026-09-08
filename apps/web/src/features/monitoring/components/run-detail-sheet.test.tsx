import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CollectorRun } from '../data/schema'
import { RunDetailSheet } from './run-detail-sheet'

afterEach(cleanup)

const partialFailedRun: CollectorRun = {
  collector_id: 'fcdaum',
  run_id: '00000000-0000-4000-8000-000000000001',
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
      outcome: 'SUCCESS',
      raw_status: 'SUCCESS_WITH_DATA',
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
      outcome: 'FAILED',
      raw_status: 'FAILED',
      source_count: 5,
      inserted_count: 0,
      changed_count: 0,
      unchanged_count: 0,
      committed: false,
      error_category: 'DB_WRITE_FAILED',
    },
    {
      unit_id: 'running-unit',
      unit_name: '진행 작업',
      attempt_no: 1,
      started_at: '2026-09-08T01:03:00Z',
      completed_at: null,
      outcome: 'RUNNING',
      raw_status: 'RUNNING',
      source_count: 0,
      inserted_count: 0,
      changed_count: 0,
      unchanged_count: 0,
      committed: null,
      error_category: null,
    },
    {
      unit_id: 'not-run-unit',
      unit_name: '미실행 작업',
      attempt_no: 1,
      started_at: '2026-09-08T01:03:00Z',
      completed_at: null,
      outcome: 'NOT_RUN',
      raw_status: 'NOT_RUN',
      source_count: 0,
      inserted_count: 0,
      changed_count: 0,
      unchanged_count: 0,
      committed: null,
      error_category: null,
    },
    {
      unit_id: 'unknown-unit',
      unit_name: '알 수 없는 작업',
      attempt_no: 1,
      started_at: '2026-09-08T01:03:00Z',
      completed_at: null,
      outcome: 'WARNING',
      raw_status: 'PAUSED_EXTERNALLY',
      source_count: 0,
      inserted_count: 0,
      changed_count: 0,
      unchanged_count: 0,
      committed: null,
      error_category: null,
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

  it('HMR 원시 SUCCESS_WITH_DATA를 canonical outcome 기준 성공으로 표시한다', () => {
    render(
      <RunDetailSheet
        open
        onOpenChange={vi.fn()}
        run={partialFailedRun}
        isLoading={false}
      />,
    )

    expect(screen.getByText('한촌설렁탕').closest('tr')?.textContent).toContain(
      '성공',
    )
  })

  it('진행·미실행·주의 canonical outcome을 성공과 구분한다', () => {
    render(
      <RunDetailSheet
        open
        onOpenChange={vi.fn()}
        run={partialFailedRun}
        isLoading={false}
      />,
    )

    const runningRow = screen.getByText('진행 작업').closest('tr')
    const notRunRow = screen.getByText('미실행 작업').closest('tr')
    const warningRow = screen.getByText('알 수 없는 작업').closest('tr')
    expect(runningRow?.textContent).toContain('실행 중')
    expect(notRunRow?.textContent).toContain('미실행')
    expect(warningRow?.textContent).toContain('주의')
    for (const row of [runningRow, notRunRow, warningRow]) {
      expect(row?.textContent).not.toContain('성공')
    }
  })
})
