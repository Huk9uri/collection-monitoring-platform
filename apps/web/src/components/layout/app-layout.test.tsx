import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { AppLayout } from './app-layout'

afterEach(cleanup)

describe('AppLayout', () => {
  it('모니터링 전용 메뉴와 main 영역을 렌더링한다', () => {
    render(
      <AppLayout>
        <h1>수집 현황</h1>
      </AppLayout>,
    )

    expect(screen.getByRole('navigation', { name: '주요 메뉴' })).toBeTruthy()
    expect(screen.getByRole('main').textContent).toContain('수집 현황')
    expect(screen.getByText('데이터 수집 모니터링')).toBeTruthy()
  })

  it('모바일 메뉴 버튼으로 Sheet 탐색을 연다', () => {
    render(<AppLayout>본문</AppLayout>)

    fireEvent.click(screen.getByRole('button', { name: '메뉴 열기' }))

    expect(screen.getByRole('dialog').textContent).toContain('모니터링')
  })
})
