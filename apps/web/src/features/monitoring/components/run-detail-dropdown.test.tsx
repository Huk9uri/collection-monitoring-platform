import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { CollectorRun } from '../data/schema'
import { RunDetailDropdown } from './run-detail-dropdown'

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

const smartPlaceRun: CollectorRun = {
  ...partialFailedRun,
  collector_id: 'smartplace',
  scope_id: 'hanchon',
  scope_name: '한촌설렁탕',
  source_count: null,
  inserted_count: null,
  changed_count: null,
  unchanged_count: null,
  attempts: [
    {
      unit_id: 'login',
      unit_name: 'login',
      attempt_no: 1,
      started_at: '2026-09-08T01:00:00Z',
      completed_at: '2026-09-08T01:00:03Z',
      outcome: 'SUCCESS',
      raw_status: 'SUCCESS',
      source_count: null,
      inserted_count: null,
      changed_count: null,
      unchanged_count: null,
      committed: null,
      error_category: null,
    },
    {
      unit_id: 'pos_linked',
      unit_name: 'pos_linked',
      attempt_no: 1,
      started_at: '2026-09-08T01:00:03Z',
      completed_at: '2026-09-08T01:01:00Z',
      outcome: 'SUCCESS',
      raw_status: 'SUCCESS',
      source_count: null,
      inserted_count: null,
      changed_count: null,
      unchanged_count: null,
      committed: true,
      error_category: null,
    },
  ],
}

describe('RunDetailDropdown', () => {
  it('부분 실패를 장애로 표시하고 성공·실패 하위 작업을 구분한다', () => {
    render(
      <RunDetailDropdown
        run={partialFailedRun}
        isLoading={false}
      />,
    )

    expect(screen.getByRole('region', { name: '실행 상세' })).toBeTruthy()
    expect(screen.queryByRole('dialog')).toBeNull()
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
      <RunDetailDropdown
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
      <RunDetailDropdown
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

  it('SmartPlace 브랜드의 login과 pos_linked 하위 작업 및 미확인 집계를 표시한다', () => {
    render(
      <RunDetailDropdown
        run={smartPlaceRun}
        isLoading={false}
      />,
    )

    expect(screen.getByText('한촌설렁탕')).toBeTruthy()
    expect(screen.getByRole('cell', { name: 'login' })).toBeTruthy()
    expect(screen.getByRole('cell', { name: 'pos_linked' })).toBeTruthy()
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })
})

it('네이버 사전 점검의 품질과 원시 결과 및 미확정 적용 집계를 구분한다', () => {
  const run = { ...smartPlaceRun, collector_id: 'naver-store-hours', status: 'WARNING' as const,
    raw_status: 'SUCCESS', execution_kind: 'preflight-only' as const,
    parent_run_id: '00000000-0000-4000-8000-000000000099',
    review_count: 2, failure_count: 0, coverage_count: null, applied_count: null, committed: false,
    attempts: [{ ...smartPlaceRun.attempts[0]!, stage: 'dry-run' as const, inserted_count: 5 }],
  }
  render(<RunDetailDropdown run={run} isLoading={false} />)
  const field = (name: string) => screen.getByText(name, { selector: 'dt' }).parentElement?.querySelector('dd')?.textContent
  expect(field('수집기')).toBe('네이버 영업시간')
  expect(field('품질 상태')).toBe('주의')
  expect(field('원시 실행 결과')).toBe('SUCCESS')
  expect(field('실행 유형')).toContain('사전 점검')
  expect(field('상위 실행 ID')).toBe(run.parent_run_id)
  expect(field('검토 매장')).toBe('2')
  expect(field('실패 매장')).toBe('0')
  expect(field('확인 매장')).toBe('-')
  expect(field('적용 매장')).toBe('-')
  expect(field('신규 확정 매장')).toBe('-')
  expect(field('DB 반영')).toBe('미반영')
  expect(screen.getByText(/요일 행 수가 아닌 매장 수/)).toBeTruthy()
  expect(screen.getByText('dry-run (예상)')).toBeTruthy()
})

it('부분 실패의 반영 확인과 예약 관측 구간을 완료나 정확한 단계 소요시간으로 표시하지 않는다', () => {
  const run = { ...partialFailedRun, collector_id: 'naver-store-hours', committed: true, applied_count: 2,
    attempts: [{ ...partialFailedRun.attempts[0]!, timing_basis: 'parent-window' as const },
      { ...partialFailedRun.attempts[1]!, timing_basis: 'worker-report' as const },
      partialFailedRun.attempts[2]!],
  }
  render(<RunDetailDropdown run={run} isLoading={false} />)
  expect(screen.getAllByText('반영 확인')).toHaveLength(2)
  expect(screen.queryByText('반영 완료')).toBeNull()
  expect(screen.getByText('예약 실행 관측 구간')).toBeTruthy()
  expect(screen.getByText('자식 실행 보고 시각')).toBeTruthy()
  expect(screen.getByText(/정확한 단계 소요시간이 아닙니다/)).toBeTruthy()
  const running = screen.getByText('진행 작업').closest('tr')!
  const timingColumn = screen.getAllByRole('columnheader').findIndex((header) => header.textContent === '시각 근거')
  expect(running.querySelectorAll('td')[timingColumn]?.textContent).toBe('-')
})
