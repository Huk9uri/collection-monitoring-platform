import {
  useIsFetching,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import { AppLayout } from '../../components/layout/app-layout'
import { CollectorCard } from './components/collector-card'
import { KpiCards } from './components/kpi-cards'
import {
  MonitoringEmpty,
  MonitoringError,
  MonitoringLoading,
  MonitoringPartialAlert,
} from './components/monitoring-state'
import { PageHeader } from './components/page-header'
import {
  MAX_RUNS_PAGE,
  RUNS_PAGE_SIZE,
  RunsTable,
  type RunFilterErrors,
  type RunFilters,
} from './components/runs-table'
import { monitoringQueries } from './data/queries'
import {
  monitoringStatusSchema,
  type CollectorRun,
  type SourceError,
  type SourceStatus,
} from './data/schema'

interface MonitoringUrlState {
  filters: RunFilters
  filterErrors: RunFilterErrors
  page: number
}

interface SelectedRun {
  collectorId: string
  runId: string
}

const MAX_RUN_RANGE_MILLISECONDS = 93 * 24 * 60 * 60 * 1_000

function parseDateInput(
  value: string | null,
  label: '시작일' | '종료일',
) {
  if (value === null || value === '') {
    return { value: '' }
  }

  const parsed = new Date(`${value}T00:00:00Z`)
  if (
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(parsed.valueOf()) &&
    parsed.toISOString().slice(0, 10) === value
  ) {
    return { value }
  }

  return {
    value: '',
    error: `올바른 조회 ${label}을 입력해 주세요.`,
  }
}

function validateDateRange(
  filters: RunFilters,
  initialErrors: RunFilterErrors = {},
): RunFilterErrors {
  const errors = { ...initialErrors }
  if (errors.from || errors.to || !filters.from || !filters.to) {
    return errors
  }

  const startedFrom = Date.parse(`${filters.from}T00:00:00.000+09:00`)
  const startedTo = Date.parse(`${filters.to}T23:59:59.999+09:00`)
  const range = startedTo - startedFrom
  if (range < 0) {
    errors.to = '조회 종료일은 시작일보다 빠를 수 없습니다.'
  } else if (range > MAX_RUN_RANGE_MILLISECONDS) {
    errors.to = '조회 기간은 최대 93일입니다.'
  }
  return errors
}

function readUrlState(): MonitoringUrlState {
  const params = new URLSearchParams(window.location.search)
  const parsedStatus = monitoringStatusSchema.safeParse(params.get('status'))
  const requestedPage = Number(params.get('page'))
  const from = parseDateInput(params.get('from'), '시작일')
  const to = parseDateInput(params.get('to'), '종료일')
  const filters: RunFilters = {
    from: from.value,
    to: to.value,
    collector: params.get('collector') ?? '',
    brand: ['hanchon', 'yuksoodang'].includes(params.get('brand') ?? '') ? params.get('brand')! : '',
    status: parsedStatus.success ? parsedStatus.data : '',
  }
  const initialErrors: RunFilterErrors = {}
  if (from.error) initialErrors.from = from.error
  if (to.error) initialErrors.to = to.error

  return {
    filters,
    filterErrors: validateDateRange(filters, initialErrors),
    page:
      Number.isInteger(requestedPage) && requestedPage > 0
        ? Math.min(requestedPage, MAX_RUNS_PAGE)
        : 1,
  }
}

function writeUrlState(state: MonitoringUrlState, replace = false) {
  const params = new URLSearchParams()
  const { filters, page } = state

  if (filters.from) params.set('from', filters.from)
  if (filters.to) params.set('to', filters.to)
  if (filters.collector) params.set('collector', filters.collector)
  if (filters.status) params.set('status', filters.status)
  if (filters.brand) params.set('brand', filters.brand)
  if (page > 1) params.set('page', String(page))

  const search = params.toString()
  const url = `${window.location.pathname}${search ? `?${search}` : ''}`
  if (replace) {
    window.history.replaceState(null, '', url)
  } else {
    window.history.pushState(null, '', url)
  }
}

function readCanonicalUrlState() {
  const state = readUrlState()
  writeUrlState(state, true)
  return state
}

function seoulDayBoundary(value: string, endOfDay: boolean) {
  if (!value) return undefined
  const time = endOfDay ? '23:59:59.999' : '00:00:00.000'
  return new Date(`${value}T${time}+09:00`).toISOString()
}

function collectSourceErrors(
  responses: Array<{ data?: { errors: SourceError[] } }>,
) {
  return responses.flatMap((response) => response.data?.errors ?? [])
}

function hasAvailableSource(
  responses: Array<{ data?: { source_status: SourceStatus } }>,
) {
  return responses.some(
    (response) =>
      response.data !== undefined &&
      response.data.source_status.succeeded > 0 &&
      !response.data.source_status.all_sources_unavailable,
  )
}

export function MonitoringPage() {
  const queryClient = useQueryClient()
  const [urlState, setUrlState] = useState(readCanonicalUrlState)
  const [selectedRun, setSelectedRun] = useState<SelectedRun | null>(null)
  const [initialQueriesSettled, setInitialQueriesSettled] = useState(false)
  const isFetching = useIsFetching({ queryKey: ['monitoring'] }) > 0

  useEffect(() => {
    const onPopState = () => setUrlState(readCanonicalUrlState())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const runConditions = useMemo(
    () => ({
      collectorId: urlState.filters.collector || undefined,
      scopeId: urlState.filters.brand || undefined,
      startedFrom: seoulDayBoundary(urlState.filters.from, false),
      startedTo: seoulDayBoundary(urlState.filters.to, true),
      status: urlState.filters.status || undefined,
      offset: (urlState.page - 1) * RUNS_PAGE_SIZE,
      pageSize: RUNS_PAGE_SIZE,
    }),
    [urlState],
  )

  const summaryQuery = useQuery(monitoringQueries.summary())
  const collectorsQuery = useQuery(monitoringQueries.collectors())
  const datesAreValid = Object.keys(urlState.filterErrors).length === 0
  const runsQuery = useQuery({
    ...monitoringQueries.runs(runConditions),
    enabled: datesAreValid,
  })
  const detailConditions = selectedRun ?? { collectorId: '', runId: '' }
  const detailQuery = useQuery({
    ...monitoringQueries.runDetail(detailConditions),
    enabled: selectedRun !== null,
  })

  const primaryQueries = [
    summaryQuery,
    collectorsQuery,
    runsQuery,
  ]
  const activePrimaryQueries = datesAreValid
    ? primaryQueries
    : [summaryQuery, collectorsQuery]
  const allPrimaryQueriesSettled = activePrimaryQueries.every(
    (query) => !query.isPending,
  )
  const initialLoading = !initialQueriesSettled && !allPrimaryQueriesSettled
  const allFailed = activePrimaryQueries.every((query) => query.isError)
  const sourceErrors = collectSourceErrors(primaryQueries)
  const hasSourceMetadata = activePrimaryQueries.some(
    (query) => query.data !== undefined,
  )
  const allSourcesUnavailable =
    allFailed ||
    (hasSourceMetadata && !hasAvailableSource(activePrimaryQueries))
  const failedAreas = [
    summaryQuery.isError ? '전체 현황' : null,
    collectorsQuery.isError ? '수집기 현황' : null,
    datesAreValid && runsQuery.isError ? '실행 이력' : null,
  ].filter((area): area is string => area !== null)
  const allEmpty =
    datesAreValid &&
    !activePrimaryQueries.some((query) => query.isError) &&
    sourceErrors.length === 0 &&
    (summaryQuery.data?.registered_collectors ?? 0) === 0 &&
    (summaryQuery.data?.today_success_runs ?? 0) === 0 &&
    (summaryQuery.data?.today_incident_runs ?? 0) === 0 &&
    (summaryQuery.data?.running_runs ?? 0) === 0 &&
    (collectorsQuery.data?.items.length ?? 0) === 0 &&
    (runsQuery.data?.items.length ?? 0) === 0

  useEffect(() => {
    if (allPrimaryQueriesSettled) {
      setInitialQueriesSettled(true)
    }
  }, [allPrimaryQueriesSettled])

  useEffect(() => {
    if (runsQuery.data === undefined) return

    const lastPage = Math.min(
      MAX_RUNS_PAGE,
      Math.max(1, Math.ceil(runsQuery.data.total / RUNS_PAGE_SIZE)),
    )
    if (urlState.page <= lastPage) return

    const correctedState = { ...urlState, page: lastPage }
    writeUrlState(correctedState, true)
    setUrlState(correctedState)
  }, [runsQuery.data, urlState])

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ['monitoring'] })
  }

  function commitUrlState(nextState: MonitoringUrlState) {
    writeUrlState(nextState)
    setUrlState(nextState)
  }

  function changeFilters(filters: RunFilters) {
    commitUrlState({
      filters,
      filterErrors: validateDateRange(filters),
      page: 1,
    })
  }

  function changePage(page: number) {
    commitUrlState({
      ...urlState,
      page: Math.max(1, Math.min(page, MAX_RUNS_PAGE)),
    })
  }

  function selectRun(run: CollectorRun) {
    setSelectedRun((current) =>
      current?.collectorId === run.collector_id && current.runId === run.run_id
        ? null
        : { collectorId: run.collector_id, runId: run.run_id },
    )
  }

  const collectorIds = Array.from(
    new Set(
      [
        ...(collectorsQuery.data?.items ?? []),
        ...(runsQuery.data?.items ?? []),
      ].map((run) => run.collector_id),
    ),
  )

  return (
    <AppLayout header={<PageHeader onRefresh={refresh} isRefreshing={isFetching} />}>
      {initialLoading ? (
        <MonitoringLoading />
      ) : allSourcesUnavailable ? (
        <MonitoringError onRetry={refresh} />
      ) : allEmpty ? (
        <MonitoringEmpty />
      ) : (
        <div className="space-y-6">
          <MonitoringPartialAlert errors={sourceErrors} failedAreas={failedAreas} />

          <KpiCards collectors={collectorsQuery.data?.items} />

          <section aria-label="수집기 현황" className="space-y-3">
            <div>
              <h2 className="text-lg font-semibold">수집기 현황</h2>
              <p className="text-sm text-muted-foreground">
                수집기별 가장 최근 실행과 작업 결과입니다.
              </p>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              {(collectorsQuery.data?.items ?? []).map((summary) => (
                <CollectorCard
                  key={summary.collector_id}
                  summary={summary}
                />
              ))}
            </div>
          </section>

          <RunsTable
            runs={runsQuery.data?.items ?? []}
            total={runsQuery.data?.total ?? 0}
            collectors={collectorIds}
            filters={urlState.filters}
            filterErrors={urlState.filterErrors}
            page={urlState.page}
            onFiltersChange={changeFilters}
            onPageChange={changePage}
            onSelectRun={selectRun}
            selectedCollectorId={selectedRun?.collectorId}
            selectedRunId={selectedRun?.runId}
            detailRun={detailQuery.data?.items[0]}
            isDetailLoading={detailQuery.isPending && selectedRun !== null}
            detailError={
              detailQuery.error ??
              (detailQuery.data?.errors.length ? detailQuery.data.errors : undefined)
            }
          />
        </div>
      )}

    </AppLayout>
  )
}
