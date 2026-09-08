import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { MonitoringStatus } from '../data/schema'
import {
  formatSeoulDateTime,
  StatusBadge,
  statusPresentation,
} from './monitoring-state'

afterEach(cleanup)

describe('모니터링 상태 표현', () => {
  it('여덟 상태를 운영자가 읽을 수 있는 한국어 표시명으로 변환한다', () => {
    const statuses: MonitoringStatus[] = [
      'SUCCESS',
      'SUCCESS_EMPTY',
      'WARNING',
      'PARTIAL_FAILED',
      'FAILED',
      'RUNNING',
      'ABORTED',
      'NOT_RUN',
    ]

    expect(statuses.map((status) => statusPresentation[status].label)).toEqual([
      '정상',
      '데이터 없음',
      '주의',
      '부분 실패',
      '실패',
      '실행 중',
      '중단',
      '미실행',
    ])
  })

  it.each(['PARTIAL_FAILED', 'FAILED', 'ABORTED'] as const)(
    '%s를 장애 심각도로 표시한다',
    (status) => {
      render(<StatusBadge status={status} />)

      expect(screen.getByText(statusPresentation[status].label).dataset.severity).toBe(
        'incident',
      )
    },
  )

  it('UTC 시각을 Asia/Seoul 시각으로 변환한다', () => {
    const formatted = formatSeoulDateTime('2026-09-08T01:05:00Z')

    expect(formatted).toContain('2026. 9. 8.')
    expect(formatted).toContain('10:05')
  })
})
