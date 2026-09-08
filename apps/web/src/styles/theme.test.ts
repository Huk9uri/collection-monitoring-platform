// @ts-expect-error 테스트 런타임의 Node 내장 모듈 타입은 앱 번들에서 제외한다.
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

const themeCss = readFileSync('src/styles/theme.css', 'utf8') as string

function tokensFor(selector: ':root' | '.dark') {
  const escapedSelector = selector.replace('.', '\\.')
  const block = themeCss.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`))
  if (!block?.[1]) throw new Error(`${selector} 토큰 블록이 없습니다.`)

  return Object.fromEntries(
    Array.from(block[1].matchAll(/--([\w-]+):\s*(#[0-9a-f]{6});/gi)).map(
      ([, name, value]) => [name, value],
    ),
  )
}

function relativeLuminance(hex: string) {
  const channels = hex
    .slice(1)
    .match(/.{2}/g)!
    .map((channel) => Number.parseInt(channel, 16) / 255)
    .map((channel) =>
      channel <= 0.04045
        ? channel / 12.92
        : ((channel + 0.055) / 1.055) ** 2.4,
    )
  return 0.2126 * channels[0]! + 0.7152 * channels[1]! + 0.0722 * channels[2]!
}

function contrastRatio(foreground: string, background: string) {
  const foregroundLuminance = relativeLuminance(foreground)
  const backgroundLuminance = relativeLuminance(background)
  return (
    (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
    (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
  )
}

describe('positive 상태 토큰 접근성', () => {
  it.each([':root', '.dark'] as const)(
    '%s positive 전경과 표면이 12px 일반 텍스트 WCAG AA 대비를 만족한다',
    (selector) => {
      const tokens = tokensFor(selector)
      const foreground = tokens['positive-foreground']
      const background = tokens['positive-surface']

      expect(foreground).toBeDefined()
      expect(background).toBeDefined()

      expect(
        contrastRatio(foreground!, background!),
      ).toBeGreaterThanOrEqual(4.5)
    },
  )
})
