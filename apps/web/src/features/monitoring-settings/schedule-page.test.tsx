import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { SchedulePage } from './schedule-page'
import { apiClient } from '../../lib/api'

const record = { collector_id: 'fcdaum', dataset_ids: ['reports'], version: '0000000000000001', updated_at: null, policy_source: 'db', warning: null,
  policy: { timezone_name: 'Asia/Seoul', max_duration_minutes: 30, start_grace_minutes: 5, schedule_attribution_window_minutes: 60,
    monitoring_enabled: true, schedules: [{ weekday_number: 1, scheduled_time: '09:00', schedule_enabled: true }], freshness: { reports: 60 } } }
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('viewer는 기준을 조회하지만 저장과 변경 이력은 제공받지 않는다', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { items: [record] } })
  render(<SchedulePage admin={false} />)
  await screen.findByText('기준 일정 조회')
  expect(screen.queryByRole('button', { name: '저장 검토' })).toBeNull()
  expect(screen.queryByRole('button', { name: '최근 변경 50건 조회' })).toBeNull()
  expect((screen.getByLabelText('시간대') as HTMLInputElement).closest('fieldset')?.disabled).toBe(true)
  expect(screen.getByText(/실제 수집기 실행 일정에는 영향을 주지 않습니다/)).toBeTruthy()
})

it('관리자는 사유 입력과 확인 후 저장하며 충돌 시 입력을 보존한다', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { items: [record] } })
  const put = vi.spyOn(apiClient, 'put').mockRejectedValue({ response: { status: 409, data: { latest: { ...record, version: '0000000000000002' } } } })
  render(<SchedulePage admin />)
  const reason = await screen.findByLabelText('변경 사유')
  fireEvent.change(reason, { target: { value: '실제 일정과 일치시킴' } })
  fireEvent.click(screen.getByRole('button', { name: '저장 검토' }))
  expect(put).not.toHaveBeenCalled()
  fireEvent.click(await screen.findByRole('button', { name: '확인하고 저장' }))
  await screen.findByText('최신 정책 비교')
  expect((reason as HTMLTextAreaElement).value).toBe('실제 일정과 일치시킴')
  fireEvent.click(screen.getByRole('button', { name: '비교 완료 · 현재 입력 유지' }))
  fireEvent.click(screen.getByRole('button', { name: '저장 검토' }))
  fireEvent.click(await screen.findByRole('button', { name: '확인하고 저장' }))
  await waitFor(() => expect(put).toHaveBeenCalledTimes(2))
  expect(put.mock.calls[1][1]).toMatchObject({ version: '0000000000000002', change_reason: '실제 일정과 일치시킴' })
})
