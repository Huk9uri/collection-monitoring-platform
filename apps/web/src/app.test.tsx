import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './app'
import { apiClient } from './lib/api'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('App', () => {
  it('세션 확인 전에는 보호 화면을 표시하지 않는다', () => {
    vi.spyOn(apiClient, 'get').mockImplementation(
      async () => await new Promise(() => undefined),
    )
    render(<App />)

    expect(
      screen.getByRole('status'),
    ).toBeTruthy()
  })
})
