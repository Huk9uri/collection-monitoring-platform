import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { freshnessRecordSchema } from '../data/schema'
import { FreshnessSummary } from './freshness-summary'

afterEach(cleanup)
const record = { collector_id: 'naver-store-hours', dataset_id: 'hanchon', scope_id: 'hanchon', scope_name: '한촌설렁탕', coverage_count: 1, source_count: 2, last_successful_check_at: '2026-09-08T01:00:00Z', latest_data_at: null, freshness_sla_minutes: 1440, freshness_overdue: false }

it('성공 수집의 브랜드와 매장 커버리지를 보존하고 미확인 업무 시각을 이력 부재와 구분한다', () => {
  render(<FreshnessSummary items={[freshnessRecordSchema.parse(record)]} />)
  expect(screen.getByText('한촌설렁탕')).toBeTruthy()
  expect(screen.getByRole('columnheader', { name: '확인 / 대상 매장' })).toBeTruthy()
  expect(screen.getByText('1 / 2')).toBeTruthy()
  expect(screen.getByText('2026. 9. 8. 10:00')).toBeTruthy()
  expect(screen.getByText('업무 시각 미확인')).toBeTruthy()
  expect(screen.queryByText('수집 이력 없음')).toBeNull()
})

it('기존 소스의 누락 커버리지는 미확인으로 표시하고 이력 문구를 유지한다', () => {
  const { scope_id: _scope, scope_name: _name, coverage_count: _coverage, source_count: _source, ...legacy } = record
  void _scope; void _name; void _coverage; void _source
  render(<FreshnessSummary items={[freshnessRecordSchema.parse({ ...legacy, collector_id: 'hmr' })]} />)
  expect(screen.getByText('hanchon')).toBeTruthy()
  expect(screen.getByText('- / -')).toBeTruthy()
  expect(screen.getByText('수집 이력 없음')).toBeTruthy()
})
