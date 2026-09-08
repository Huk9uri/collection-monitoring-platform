import { describe, expect, it } from 'vitest'

import { apiClient, resolveApiTimeout } from './api'

describe('API 요청 timeout', () => {
  it('환경 변수가 없으면 API 소스 deadline보다 긴 40초 timeout을 사용한다', () => {
    expect(resolveApiTimeout(undefined)).toBe(40_000)
    expect(apiClient.defaults.timeout).toBe(40_000)
  })

  it('양수 정수 환경 변수를 밀리초 timeout으로 사용한다', () => {
    expect(resolveApiTimeout('2500')).toBe(2_500)
  })

  it.each(['0', '-1', '1.5', 'not-a-number'])(
    '잘못된 timeout %s 설정을 시작 시 거부한다',
    (configured) => {
      expect(() => resolveApiTimeout(configured)).toThrow(
        'VITE_MONITORING_API_TIMEOUT_MS',
      )
    },
  )
})
