import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { CollectorSummary, MonitoringStatus } from '../data/schema'
import { KpiCards } from './kpi-cards'

afterEach(cleanup)

function collector(
  collectorId: string,
  status: MonitoringStatus,
): CollectorSummary {
  return {
    collector_id: collectorId,
    display_name: collectorId,
    status,
    latest_run: null,
    schedule_timezone: null,
    daily_scheduled_time: null,
    max_duration_minutes: null,
    last_successful_check_at: null,
    latest_data_at: null,
    freshness_overdue: false,
    freshness: [],
  }
}

describe('KpiCards', () => {
  it('수집기 카드와 같은 최신 상태를 기존 심각도 기준으로 집계한다', () => {
    const collectors = [
      collector('success', 'SUCCESS'),
      collector('success-empty', 'SUCCESS_EMPTY'),
      collector('warning', 'WARNING'),
      collector('partial-failed', 'PARTIAL_FAILED'),
      collector('failed', 'FAILED'),
      collector('aborted', 'ABORTED'),
      collector('running', 'RUNNING'),
      collector('not-run', 'NOT_RUN'),
    ]

    render(<KpiCards collectors={collectors} />)

    const summary = screen.getByRole('region', { name: '수집기 상태 요약' })
    expect(summary.textContent).toContain('수집기별 가장 최근 실행 상태')
    expect(summary.textContent).toContain('전체 수집기8')
    expect(summary.textContent).toContain('정상2')
    expect(summary.textContent).toContain('주의1')
    expect(summary.textContent).toContain('장애3')
    expect(summary.textContent).toContain('실행 중1')
    expect(summary.textContent).toContain('미실행1')
    expect(summary.textContent).not.toContain('오늘 정상')
    expect(summary.textContent).not.toContain('오늘 장애')
  })
})
