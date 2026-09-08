import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './app'
import { apiClient } from './lib/api'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('App', () => {
  it('데이터 수집 모니터링 제목을 표시한다', () => {
    vi.spyOn(apiClient, 'get').mockImplementation(
      async () => await new Promise(() => undefined),
    )
    render(<App />)

    expect(
      screen.getByRole('heading', { name: '데이터 수집 모니터링' }),
    ).toBeTruthy()
  })
})
