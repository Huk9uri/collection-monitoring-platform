import { describe, expect, it } from 'vitest'

import { formatCount } from './format-count'

describe('formatCount', () => {
  it('미확인 집계는 0이 아닌 대시로 표시한다', () => {
    expect(formatCount(null)).toBe('-')
  })

  it('확인된 집계는 한국어 숫자 형식으로 표시한다', () => {
    expect(formatCount(1234)).toBe('1,234')
  })
})
