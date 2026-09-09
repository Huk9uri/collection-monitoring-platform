import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CollectorRun } from '../data/schema'
import { RunsTable } from './runs-table'

afterEach(cleanup)

const smartPlaceRun: CollectorRun = {
  collector_id: 'smartplace',
  run_id: '00000000-0000-4000-8000-000000000001',
  scheduled_date: '2026-09-09',
  started_at: '2026-09-09T01:00:00Z',
  completed_at: '2026-09-09T01:03:00Z',
  status: 'SUCCESS',
  successful_units: 2,
  failed_units: 0,
  scope_id: 'hanchon',
  scope_name: '한촌설렁탕',
  source_count: null,
  inserted_count: null,
  changed_count: null,
  unchanged_count: null,
  attempts: [],
}

describe('RunsTable', () => {
  it('SmartPlace 실행을 브랜드별 행과 미확인 집계로 표시한다', () => {
    render(
      <RunsTable
        runs={[smartPlaceRun]}
        total={1}
        collectors={['smartplace']}
        filters={{ from: '', to: '', collector: '', status: '' }}
        filterErrors={{}}
        page={1}
        onFiltersChange={vi.fn()}
        onPageChange={vi.fn()}
        onSelectRun={vi.fn()}
      />,
    )

    expect(screen.getByRole('cell', { name: '한촌설렁탕' })).toBeTruthy()
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  it('실행 이력에서 수집기 제어 버튼을 제공하지 않는다', () => {
    render(
      <RunsTable
        runs={[smartPlaceRun]}
        total={1}
        collectors={['smartplace']}
        filters={{ from: '', to: '', collector: '', status: '' }}
        filterErrors={{}}
        page={1}
        onFiltersChange={vi.fn()}
        onPageChange={vi.fn()}
        onSelectRun={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: /재실행|중지|재시도/ })).toBeNull()
  })
})
