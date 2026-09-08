import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { App } from './app'

describe('App', () => {
  it('데이터 수집 모니터링 제목을 표시한다', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { name: '데이터 수집 모니터링' }),
    ).toBeTruthy()
  })
})
