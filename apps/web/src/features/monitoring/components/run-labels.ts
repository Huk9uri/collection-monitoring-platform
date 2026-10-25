import type { CollectorRun } from '../data/schema'

export function executionKindLabel(kind: CollectorRun['execution_kind']) {
  if (kind == null) return '-'
  return {
    scheduled: '정기 실행',
    manual: '수동 실행',
    backfill: '과거 데이터 보충',
    'preflight-only': '사전 점검 전용',
  }[kind]
}

export function targetKindLabel(kind: CollectorRun['target_kind']) {
  if (kind == null) return '-'
  return {
    'all-stores': '전체 매장',
    'single-store': '단일 매장',
    'date-range': '기간 지정',
  }[kind]
}
