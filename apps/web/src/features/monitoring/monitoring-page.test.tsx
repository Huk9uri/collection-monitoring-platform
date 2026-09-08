import {
  QueryClient,
  QueryClientProvider,
  type QueryClientConfig,
} from '@tanstack/react-query'
import {
  act,
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
  CollectorSummary,
  FreshnessRecord,
  SourceError,
  SourceStatus,
  SummaryResponse,
} from './data/schema'
import { MonitoringPage } from './monitoring-page'

const successfulRun: CollectorRun = {
  collector_id: 'hmr',
  run_id: '00000000-0000-4000-8000-000000000001',
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
  run_id: '00000000-0000-4000-8000-000000000002',
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
      outcome: 'SUCCESS',
      raw_status: 'SUCCESS_WITH_DATA',
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
      outcome: 'FAILED',
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

const failedRun: CollectorRun = {
  ...successfulRun,
  run_id: '00000000-0000-4000-8000-000000000003',
  status: 'FAILED',
  successful_units: 0,
  failed_units: 1,
}

const freshness: FreshnessRecord[] = [
  {
    collector_id: 'hmr',
    dataset_id: 'orders',
    last_successful_check_at: '2026-09-08T01:05:00Z',
    latest_data_at: '2026-09-08T00:55:00Z',
    freshness_sla_minutes: 180,
    freshness_overdue: false,
  },
  {
    collector_id: 'fcdaum',
    dataset_id: 'missions',
    last_successful_check_at: '2026-09-08T01:03:00Z',
    latest_data_at: null,
    freshness_sla_minutes: 60,
    freshness_overdue: true,
  },
]

const sourceError: SourceError = {
  collector_id: 'fcdaum',
  code: 'SOURCE_UNAVAILABLE',
  message: '데이터 소스를 조회할 수 없습니다.',
}

const availableSourceStatus: SourceStatus = {
  registered: 2,
  succeeded: 2,
  failed: 0,
  all_sources_unavailable: false,
}

const baseSummary: SummaryResponse = {
  overall_status: 'PARTIAL_FAILED',
  registered_collectors: 2,
  today_success_runs: 3,
  today_incident_runs: 1,
  running_runs: 0,
  errors: [],
  source_status: availableSourceStatus,
}

function toCollectorSummary(run: CollectorRun): CollectorSummary {
  return {
    collector_id: run.collector_id,
    display_name: run.collector_id === 'hmr' ? 'HMR' : 'FC다움',
    status: run.status,
    latest_run: run,
    schedule_timezone: 'Asia/Seoul',
    daily_scheduled_time: '03:00:00',
    max_duration_minutes: 120,
    last_successful_check_at:
      run.status === 'SUCCESS' || run.status === 'SUCCESS_EMPTY'
        ? run.completed_at
        : null,
    latest_data_at: run.completed_at,
    freshness_overdue: false,
    freshness: freshness.filter(
      (item) => item.collector_id === run.collector_id,
    ),
  }
}

interface ApiScenario {
  runs?: CollectorRun[]
  collectors?: CollectorSummary[]
  errors?: SourceError[]
  sourceStatus?: SourceStatus
  summary?: SummaryResponse
  total?: number
  pending?: boolean
  rejectAll?: boolean
}

function mockApi({
  runs = [successfulRun, partialFailedRun],
  collectors = runs.map(toCollectorSummary),
  errors = [],
  sourceStatus = errors.length > 0
    ? {
        registered: 2,
        succeeded: 1,
        failed: 1,
        all_sources_unavailable: false,
      }
    : availableSourceStatus,
  summary = {
    ...baseSummary,
    overall_status: runs.length === 0 ? 'NOT_RUN' : baseSummary.overall_status,
    registered_collectors: collectors.length,
    today_success_runs: runs.filter(
      (run) => run.status === 'SUCCESS' || run.status === 'SUCCESS_EMPTY',
    ).length,
    today_incident_runs: runs.filter(
      (run) =>
        run.status === 'PARTIAL_FAILED' ||
        run.status === 'FAILED' ||
        run.status === 'ABORTED',
    ).length,
    running_runs: runs.filter((run) => run.status === 'RUNNING').length,
    errors,
    source_status: sourceStatus,
  },
  total = runs.length,
  pending = false,
  rejectAll = false,
}: ApiScenario = {}) {
  return vi.spyOn(apiClient, 'get').mockImplementation(async (path, config) => {
    if (pending) {
      await new Promise(() => undefined)
    }
    if (rejectAll) {
      throw new Error('network unavailable')
    }

    const url = String(path)
    const params = config?.params as Record<string, unknown> | undefined
    const requestedStatus = params?.status
    const serverRuns = requestedStatus
      ? runs.filter((run) => run.status === requestedStatus)
      : runs
    const data = url.endsWith('/summary')
      ? summary
      : url.endsWith('/collectors')
        ? { items: collectors, errors, source_status: sourceStatus }
      : url.endsWith('/runs')
        ? { items: serverRuns, errors, source_status: sourceStatus, total }
        : url.includes('/runs/')
          ? {
              items: [partialFailedRun],
              errors: [],
              source_status: availableSourceStatus,
            }
          : undefined

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

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
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

  it('필수 초기 조회는 서로 다른 순서로 완료되어도 모두 settled될 때까지 로딩을 유지한다', async () => {
    const collectors = deferred<never>()
    const runs = deferred<never>()
    vi.spyOn(apiClient, 'get').mockImplementation(async (path) => {
      const url = String(path)
      if (url.endsWith('/summary')) {
        return {
          data: {
            ...baseSummary,
            overall_status: 'NOT_RUN',
            registered_collectors: 0,
            today_success_runs: 0,
            today_incident_runs: 0,
            running_runs: 0,
          },
        } as never
      }
      if (url.endsWith('/collectors')) return collectors.promise
      return runs.promise
    })
    renderPage()

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledTimes(3)
    })
    expect(screen.getByRole('status', {
      name: '모니터링 데이터를 불러오는 중입니다.',
    })).toBeTruthy()

    await act(async () => {
      collectors.resolve({
        data: {
          items: [],
          errors: [],
          source_status: availableSourceStatus,
        },
      } as never)
    })
    expect(screen.getByRole('status', {
      name: '모니터링 데이터를 불러오는 중입니다.',
    })).toBeTruthy()

    await act(async () => {
      runs.resolve({
        data: {
          items: [],
          errors: [],
          source_status: availableSourceStatus,
          total: 0,
        },
      } as never)
    })
    expect(await screen.findByRole('status', {
      name: '표시할 모니터링 데이터가 없습니다.',
    })).toBeTruthy()
  })

  it('모든 조회 결과가 비어 있으면 빈 결과 상태를 표시한다', async () => {
    mockApi({ runs: [] })
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

  it.each([
    {
      name: '등록된 두 소스가 모두 실패',
      sourceStatus: {
        registered: 2,
        succeeded: 0,
        failed: 2,
        all_sources_unavailable: true,
      },
      errors: [sourceError],
    },
    {
      name: '등록 소스 없음',
      sourceStatus: {
        registered: 0,
        succeeded: 0,
        failed: 0,
        all_sources_unavailable: true,
      },
      errors: [],
    },
  ])('$name이면 HTTP 200이어도 전체 오류를 표시한다', async ({ sourceStatus, errors }) => {
    mockApi({
      runs: [],
      collectors: [],
      errors,
      sourceStatus,
      summary: {
        overall_status: 'NOT_RUN',
        registered_collectors: sourceStatus.registered,
        today_success_runs: 0,
        today_incident_runs: 0,
        running_runs: 0,
        errors,
        source_status: sourceStatus,
      },
    })
    renderPage()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('모니터링 데이터를 불러오지 못했습니다.')
    expect(alert.textContent).not.toContain('일부 데이터를')
  })

  it('KPI와 수집기·신선도·실행 이력에 실제 조회 결과를 표시한다', async () => {
    mockApi({ summary: baseSummary })
    renderPage()

    const kpis = await screen.findByRole('region', { name: '전체 현황' })
    expect(kpis.textContent).toContain('전체 수집기2')
    expect(kpis.textContent).toContain('오늘 정상3')
    expect(kpis.textContent).toContain('오늘 장애1')
    expect(screen.getByRole('article', { name: 'HMR 최신 상태' })).toBeTruthy()
    expect(screen.getByRole('article', { name: 'FC다움 최신 상태' })).toBeTruthy()
    expect(screen.getByRole('table', { name: '데이터 신선도' })).toBeTruthy()
    expect(screen.getByText('마지막 성공 확인')).toBeTruthy()
    expect(screen.getByText('최신 데이터 시각')).toBeTruthy()
    expect(screen.getByText('SLA 초과')).toBeTruthy()
    expect(screen.getByRole('table', { name: '수집 실행 이력' })).toBeTruthy()
  })

  it('수집기 snapshot의 중첩 신선도를 표시하고 freshness endpoint는 호출하지 않는다', async () => {
    const snapshotFreshness: FreshnessRecord = {
      ...freshness[0]!,
      dataset_id: 'collector-snapshot',
    }
    const collector = {
      ...toCollectorSummary(successfulRun),
      freshness: [snapshotFreshness],
    }
    const request = mockApi({
      collectors: [collector],
    })

    renderPage()

    expect(await screen.findByText('collector-snapshot')).toBeTruthy()
    expect(
      request.mock.calls.some(([path]) => String(path).endsWith('/freshness')),
    ).toBe(false)
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
    expect(screen.queryByText(successfulRun.run_id)).toBeNull()
    expect(screen.getByText(partialFailedRun.run_id)).toBeTruthy()
    expect(request).toHaveBeenCalledWith('/api/v1/monitoring/runs', {
      params: {
        collector_id: 'fcdaum',
        started_from: '2026-08-31T15:00:00.000Z',
        started_to: '2026-09-08T14:59:59.999Z',
        status: 'PARTIAL_FAILED',
        offset: 20,
        page_size: 20,
      },
    })
  })

  it('형식이 잘못된 URL 날짜를 제거하고 필드 오류를 표시하며 실행 조회를 막는다', async () => {
    window.history.replaceState(null, '', '/?from=2026-02-31&collector=hmr')
    const request = mockApi()
    renderPage()

    expect(await screen.findByText('올바른 조회 시작일을 입력해 주세요.')).toBeTruthy()
    await waitFor(() => {
      const search = new URLSearchParams(window.location.search)
      expect(search.get('from')).toBeNull()
      expect(search.get('collector')).toBe('hmr')
    })
    expect(screen.getByLabelText('조회 시작일')).toHaveProperty('value', '')
    expect(
      request.mock.calls.some(([path]) => String(path).endsWith('/runs')),
    ).toBe(false)
  })

  it('역전된 날짜 범위를 입력 옆에서 알리고 실행 조회를 보내지 않는다', async () => {
    window.history.replaceState(
      null,
      '',
      '/?from=2026-09-09&to=2026-09-08',
    )
    const request = mockApi()
    renderPage()

    expect(
      await screen.findByText('조회 종료일은 시작일보다 빠를 수 없습니다.'),
    ).toBeTruthy()
    expect(screen.getByLabelText('조회 종료일').getAttribute('aria-invalid')).toBe(
      'true',
    )
    expect(
      request.mock.calls.some(([path]) => String(path).endsWith('/runs')),
    ).toBe(false)
  })

  it('93일을 초과한 날짜 범위를 입력 옆에서 알리고 실행 조회를 보내지 않는다', async () => {
    window.history.replaceState(
      null,
      '',
      '/?from=2026-06-01&to=2026-09-09',
    )
    const request = mockApi()
    renderPage()

    expect(await screen.findByText('조회 기간은 최대 93일입니다.')).toBeTruthy()
    expect(
      request.mock.calls.some(([path]) => String(path).endsWith('/runs')),
    ).toBe(false)
  })

  it('초기 URL의 과도한 페이지를 서버 최대 페이지로 즉시 정규화한다', async () => {
    window.history.replaceState(null, '', '/?page=999')
    mockApi({ total: 20_000 })
    renderPage()

    await screen.findByRole('table', { name: '수집 실행 이력' })
    expect(new URLSearchParams(window.location.search).get('page')).toBe('501')
    expect(screen.getByText(/501\/501 페이지/)).toBeTruthy()
  })

  it('popstate로 복원된 URL도 화면 상태와 같은 canonical 값으로 교체한다', async () => {
    mockApi({ total: 20_000 })
    renderPage()
    await screen.findByRole('table', { name: '수집 실행 이력' })

    act(() => {
      window.history.pushState(null, '', '/?page=999&from=invalid')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })

    expect(await screen.findByText('올바른 조회 시작일을 입력해 주세요.')).toBeTruthy()
    await waitFor(() => {
      const search = new URLSearchParams(window.location.search)
      expect(search.get('page')).toBe('501')
      expect(search.get('from')).toBeNull()
    })
    expect(screen.getByLabelText('조회 시작일')).toHaveProperty('value', '')
  })

  it('상태 필터를 서버 페이지네이션 전에 적용해 뒤 페이지의 일치 실행을 찾는다', async () => {
    window.history.replaceState(null, '', '/?status=FAILED')
    const firstUnfilteredPage = Array.from({ length: 20 }, (_, index) => ({
      ...successfulRun,
      run_id: `00000000-0000-4000-8000-${String(index + 10).padStart(12, '0')}`,
    }))
    const request = vi.spyOn(apiClient, 'get').mockImplementation(
      async (path, config) => {
        const url = String(path)
        const params = config?.params as Record<string, unknown> | undefined
        if (url.endsWith('/runs')) {
          return {
            data:
              params?.status === 'FAILED'
                ? {
                    items: [failedRun],
                    errors: [],
                    source_status: availableSourceStatus,
                    total: 1,
                  }
                : {
                    items: firstUnfilteredPage,
                    errors: [],
                    source_status: availableSourceStatus,
                    total: 21,
                  },
          } as never
        }
        if (url.endsWith('/summary')) return { data: baseSummary } as never
        return {
          data: {
            items: [toCollectorSummary(successfulRun)],
            errors: [],
            source_status: availableSourceStatus,
          },
        } as never
      },
    )
    renderPage()

    expect(await screen.findByText(failedRun.run_id)).toBeTruthy()
    expect(screen.queryByText(firstUnfilteredPage[0]!.run_id)).toBeNull()
    expect(request).toHaveBeenCalledWith('/api/v1/monitoring/runs', {
      params: expect.objectContaining({ status: 'FAILED', offset: 0 }),
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
          status: undefined,
          offset: 20,
          page_size: 20,
        },
      })
    })
  })

  it('URL 페이지가 필터 결과의 마지막 페이지를 넘으면 URL과 offset을 안전하게 보정한다', async () => {
    window.history.replaceState(null, '', '/?status=FAILED&page=5')
    const request = mockApi({ runs: [failedRun], total: 20 })
    renderPage()

    await waitFor(() => {
      expect(new URLSearchParams(window.location.search).get('page')).toBeNull()
      expect(screen.getByText(/1\/1 페이지/)).toBeTruthy()
    })

    const runRequests = request.mock.calls.filter(
      ([path]) => String(path).endsWith('/runs'),
    )
    expect(runRequests).toHaveLength(2)
    expect(runRequests[0]?.[1]?.params).toMatchObject({ offset: 80 })
    expect(runRequests[1]?.[1]?.params).toMatchObject({ offset: 0 })
  })

  it('서버 최대 offset 페이지에서는 전체 건수가 더 커도 다음 이동을 막는다', async () => {
    window.history.replaceState(null, '', '/?page=501')
    mockApi({ total: 20_000 })
    renderPage()

    const nextPage = await screen.findByRole('button', { name: '다음 페이지' })

    expect(nextPage).toHaveProperty('disabled', true)
  })

  it('새로고침은 summary·collectors·runs 세 화면 조회만 다시 실행한다', async () => {
    const request = mockApi()
    const { queryClient } = renderPage()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    await screen.findByRole('table', { name: '수집 실행 이력' })
    request.mockClear()

    fireEvent.click(screen.getByRole('button', { name: '새로고침' }))

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['monitoring'] })
    await waitFor(() => expect(request).toHaveBeenCalledTimes(3))
    expect(
      request.mock.calls.map(([path]) => String(path).split('/').at(-1)).sort(),
    ).toEqual(['collectors', 'runs', 'summary'])
  })

  it('실행을 선택하면 상세를 조회해 서울 시각과 하위 작업을 표시한다', async () => {
    const request = mockApi()
    renderPage()
    await screen.findByRole('table', { name: '수집 실행 이력' })

    fireEvent.click(
      screen.getByRole('button', {
        name: `실행 ${partialFailedRun.run_id} 상세 보기`,
      }),
    )

    const dialog = await screen.findByRole('dialog', { name: '실행 상세' })
    expect(await within(dialog).findByText('한촌설렁탕')).toBeTruthy()
    expect(within(dialog).getByText('2026. 9. 8. 10:00')).toBeTruthy()
    expect(request).toHaveBeenCalledWith(
      `/api/v1/monitoring/runs/fcdaum/${partialFailedRun.run_id}`,
      undefined,
    )
  })
})
