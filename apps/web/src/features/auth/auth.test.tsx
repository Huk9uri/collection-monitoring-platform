import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthGate, safeReturnTo } from './auth-gate'
import { apiClient } from '../../lib/api'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('로그인 경계', () => {
  it('외부 복귀 경로를 차단한다', () => {
    for (const value of ['https://evil.test', '//evil.test', '/\\evil.test', '/login']) {
      expect(safeReturnTo(value)).toBe('/')
    }
    expect(safeReturnTo('/?status=FAILED')).toBe('/?status=FAILED')
  })
  it('비로그인 사용자는 데이터 대신 로그인 폼을 본다', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValue({ response: { status: 401 } })
    render(<AuthGate onExpired={() => undefined}>{() => <div>보호 데이터</div>}</AuthGate>)
    await screen.findByRole('button', { name: '로그인' })
    expect(screen.queryByText('보호 데이터')).toBeNull()
  })
  it('로그인 성공 후에만 데이터를 표시한다', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValue({ response: { status: 401 } })
    vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { user: { username: 'viewer', roles: ['viewer'] }, csrf_token: 'token' } })
    render(<AuthGate onExpired={() => undefined}>{() => <div>보호 데이터</div>}</AuthGate>)
    fireEvent.change(await screen.findByLabelText('아이디'), { target: { value: 'viewer' } })
    fireEvent.change(screen.getByLabelText('비밀번호'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: '로그인' }))
    await waitFor(() => expect(screen.getByText('보호 데이터')).toBeTruthy())
  })
})
