import {
  QueryClient,
  QueryClientProvider,
  type QueryClientConfig,
} from '@tanstack/react-query'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '../../lib/api'
import type {
  CollectorRun,
  FreshnessRecord,
  SourceError,
} from './data/schema'
import { MonitoringPage } from './monitoring-page'

const successfulRun: CollectorRun = {
  collector_id: 'hmr',
  run_id: 'run-success',
  scheduled_date: '2026-09-08',
  started_at: '2026-09-08T01:00:00Z',
  completed_at: '2026-09-08T01:03:00Z',
  status: 'SUCCESS',
  successful_units: 2,
  failed_units: 0,
  source_count: 10,
  inserted_count: 4,
  changed_count: 2,
  unchanged_count: 4,
  attempts: [],
}

const partialFailedRun: CollectorRun = {
  ...successfulRun,
  collector_id: 'fcdaum',
  run_id: 'run-partial',
  status: 'PARTIAL_FAILED',
  successful_units: 1,
  failed_units: 1,
  attempts: [
    {
      unit_id: 'hanchon',
      unit_name: '한촌설렁탕',
      attempt_no: 1,
      started_at: '2026-09-08T01:00:00Z',
      completed_at: '2026-09-08T01:01:00Z',
      raw_status: 'SUCCESS',
      source_count: 5,
      inserted_count: 2,
      changed_count: 1,
      unchanged_count: 2,
      committed: true,
      error_category: null,
    },
    {
      unit_id: 'yuksudang',
      unit_name: '육수당',
      attempt_no: 1,
      started_at: '2026-09-08T01:01:00Z',
      completed_at: '2026-09-08T01:02:00Z',
      raw_status: 'FAILED',
      source_count: 5,
      inserted_count: 0,
      changed_count: 0,
      unchanged_count: 0,
      committed: false,
      error_category: 'DB_WRITE_FAILED',
    },
  ],
}

const freshness: FreshnessRecord[] = [
  {
    collector_id: 'hmr',
    dataset_id: 'orders',
    latest_at: '2026-09-08T01:05:00Z',
  },
  {
    collector_id: 'fcdaum',
    dataset_id: 'missions',
    latest_at: null,
  },
]

const sourceError: SourceError = {
  collector_id: 'fcdaum',
  code: 'SOURCE_UNAVAILABLE',
  message: '데이터 소스를 조회할 수 없습니다.',
}

interface ApiScenario {
  runs?: CollectorRun[]
  freshness?: FreshnessRecord[]
  errors?: SourceError[]
  total?: number
  pending?: boolean
  rejectAll?: boolean
}

function mockApi({
  runs = [successfulRun, partialFailedRun],
  freshness: freshnessItems = freshness,
  errors = [],
  total = runs.length,
  pending = false,
  rejectAll = false,
}: ApiScenario = {}) {
  return vi.spyOn(apiClient, 'get').mockImplementation(async (path) => {
    if (pending) {
      await new Promise(() => undefined)
    }
    if (rejectAll) {
      throw new Error('network unavailable')
    }

    const url = String(path)
    const data = url.endsWith('/freshness')
      ? { items: freshnessItems, errors }
      : url.endsWith('/runs')
        ? { items: runs, errors, total }
        : url.includes('/runs/')
          ? { items: [partialFailedRun], errors: [] }
          : { items: runs, errors }

    return { data } as never
  })
}

const queryClientConfig: QueryClientConfig = {
  defaultOptions: {
    queries: {
      retry: false,
      gcTime: 0,
    },
  },
}

function renderPage() {
  const queryClient = new QueryClient(queryClientConfig)
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MonitoringPage />
    </QueryClientProvider>,
  )

  return { ...result, queryClient }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.history.replaceState(null, '', '/')
})

describe('MonitoringPage', () => {
  it('읽기 전용 헤더에 제목과 수동 새로고침만 제공한다', () => {
    mockApi({ pending: true })
    renderPage()

    expect(
      screen.getByRole('heading', { name: '데이터 수집 모니터링' }),
    ).toBeTruthy()
    expect(screen.getByRole('button', { name: '새로고침' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /실행/ })).toBeNull()
  })

  it('첫 조회 중에는 접근 가능한 로딩 상태를 표시한다', () => {
    mockApi({ pending: true })
    renderPage()

    expect(
      screen.getByRole('status', {
        name: '모니터링 데이터를 불러오는 중입니다.',
      }),
    ).toBeTruthy()
  })

  it('모든 조회 결과가 비어 있으면 빈 결과 상태를 표시한다', async () => {
    mockApi({ runs: [], freshness: [] })
    renderPage()

    expect(
      await screen.findByRole('status', {
        name: '표시할 모니터링 데이터가 없습니다.',
      }),
    ).toBeTruthy()
  })

  it('모든 조회가 실패하면 전체 오류와 재시도 수단을 표시한다', async () => {
    mockApi({ rejectAll: true })
    renderPage()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('모니터링 데이터를 불러오지 못했습니다.')
    expect(within(alert).getByRole('button', { name: '다시 시도' })).toBeTruthy()
  })

  it('부분 데이터 소스 장애를 알리면서 정상 결과와 네 영역을 유지한다', async () => {
    mockApi({ errors: [sourceError] })
    renderPage()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('FC다움')
    expect(alert.textContent).toContain('데이터 소스를 조회할 수 없습니다.')
    expect(screen.getByRole('region', { name: '전체 현황' })).toBeTruthy()
    expect(screen.getByRole('region', { name: '수집기 현황' })).toBeTruthy()
    expect(screen.getByRole('region', { name: '데이터 신선도' })).toBeTruthy()
    expect(screen.getByRole('region', { name: '실행 이력' })).toBeTruthy()
    expect(screen.getByRole('main')).toBeTruthy()
  })

  it('KPI와 수집기·신선도·실행 이력에 실제 조회 결과를 표시한다', async () => {
    mockApi()
    renderPage()

    const kpis = await screen.findByRole('region', { name: '전체 현황' })
    expect(kpis.textContent).toContain('전체 수집기')
    expect(kpis.textContent).toContain('장애')
    expect(screen.getByRole('article', { name: 'HMR 최신 상태' })).toBeTruthy()
    expect(screen.getByRole('article', { name: 'FC다움 최신 상태' })).toBeTruthy()
    expect(screen.getByRole('table', { name: '데이터 신선도' })).toBeTruthy()
    expect(screen.getByRole('table', { name: '수집 실행 이력' })).toBeTruthy()
  })

  it('URL의 날짜·수집기·상태·페이지를 조회와 화면 필터에 적용한다', async () => {
    window.history.replaceState(
      null,
      '',
      '/?from=2026-09-01&to=2026-09-08&collector=fcdaum&status=PARTIAL_FAILED&page=2',
    )
    const request = mockApi({ total: 45 })
    renderPage()

    await screen.findByRole('table', { name: '수집 실행 이력' })

    expect(screen.getByLabelText('조회 시작일')).toHaveProperty(
      'value',
      '2026-09-01',
    )
    expect(screen.getByLabelText('조회 종료일')).toHaveProperty(
      'value',
      '2026-09-08',
    )
    expect(screen.getByLabelText('수집기 필터')).toHaveProperty('value', 'fcdaum')
    expect(screen.getByLabelText('상태 필터')).toHaveProperty(
      'value',
      'PARTIAL_FAILED',
    )
    expect(screen.queryByText('run-success')).toBeNull()
    expect(screen.getByText('run-partial')).toBeTruthy()
    expect(request).toHaveBeenCalledWith('/api/v1/monitoring/runs', {
      params: {
        collector_id: 'fcdaum',
        started_from: '2026-08-31T15:00:00.000Z',
        started_to: '2026-09-08T14:59:59.999Z',
        offset: 20,
        page_size: 20,
      },
    })
  })

  it('필터 변경은 URL을 갱신하고 첫 페이지에서 서버 조회를 다시 시작한다', async () => {
    window.history.replaceState(null, '', '/?page=3')
    mockApi({ total: 100 })
    renderPage()
    await screen.findByRole('table', { name: '수집 실행 이력' })

    fireEvent.change(screen.getByLabelText('수집기 필터'), {
      target: { value: 'hmr' },
    })

    await waitFor(() => {
      const search = new URLSearchParams(window.location.search)
      expect(search.get('collector')).toBe('hmr')
      expect(search.get('page')).toBeNull()
    })
  })

  it('다음 페이지는 URL과 서버 offset을 함께 갱신한다', async () => {
    const request = mockApi({ total: 45 })
    renderPage()
    await screen.findByRole('table', { name: '수집 실행 이력' })

    fireEvent.click(screen.getByRole('button', { name: '다음 페이지' }))

    await waitFor(() => {
      expect(new URLSearchParams(window.location.search).get('page')).toBe('2')
      expect(request).toHaveBeenCalledWith('/api/v1/monitoring/runs', {
        params: {
          collector_id: undefined,
          started_from: undefined,
          started_to: undefined,
          offset: 20,
          page_size: 20,
        },
      })
    })
  })

  it('서버 최대 offset 페이지에서는 전체 건수가 더 커도 다음 이동을 막는다', async () => {
    window.history.replaceState(null, '', '/?page=501')
    mockApi({ total: 20_000 })
    renderPage()

    const nextPage = await screen.findByRole('button', { name: '다음 페이지' })

    expect(nextPage).toHaveProperty('disabled', true)
  })

  it('새로고침은 monitoring query만 수동으로 invalidate한다', async () => {
    mockApi()
    const { queryClient } = renderPage()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    await screen.findByRole('table', { name: '수집 실행 이력' })

    fireEvent.click(screen.getByRole('button', { name: '새로고침' }))

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['monitoring'] })
  })

  it('실행을 선택하면 상세를 조회해 서울 시각과 하위 작업을 표시한다', async () => {
    const request = mockApi()
    renderPage()
    await screen.findByRole('table', { name: '수집 실행 이력' })

    fireEvent.click(
      screen.getByRole('button', { name: '실행 run-partial 상세 보기' }),
    )

    const dialog = await screen.findByRole('dialog', { name: '실행 상세' })
    expect(await within(dialog).findByText('한촌설렁탕')).toBeTruthy()
    expect(within(dialog).getByText('2026. 9. 8. 10:00')).toBeTruthy()
    expect(request).toHaveBeenCalledWith(
      '/api/v1/monitoring/runs/fcdaum/run-partial',
      undefined,
    )
  })
})
