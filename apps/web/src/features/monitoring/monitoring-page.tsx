import {
  useIsFetching,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import { AppLayout } from '../../components/layout/app-layout'
import { CollectorCard } from './components/collector-card'
import { FreshnessSummary } from './components/freshness-summary'
import { KpiCards } from './components/kpi-cards'
import {
  MonitoringEmpty,
  MonitoringError,
  MonitoringLoading,
  MonitoringPartialAlert,
} from './components/monitoring-state'
import { PageHeader } from './components/page-header'
import { RunDetailSheet } from './components/run-detail-sheet'
import {
  MAX_RUNS_PAGE,
  RUNS_PAGE_SIZE,
  RunsTable,
  type RunFilters,
} from './components/runs-table'
import { monitoringQueries } from './data/queries'
import {
  monitoringStatusSchema,
  type CollectorRun,
  type SourceError,
} from './data/schema'

interface MonitoringUrlState {
  filters: RunFilters
  page: number
}

interface SelectedRun {
  collectorId: string
  runId: string
}

function validDateInput(value: string | null) {
  if (value === null || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return ''
  }

  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
    ? value
    : ''
}

function readUrlState(): MonitoringUrlState {
  const params = new URLSearchParams(window.location.search)
  const parsedStatus = monitoringStatusSchema.safeParse(params.get('status'))
  const requestedPage = Number(params.get('page'))

  return {
    filters: {
      from: validDateInput(params.get('from')),
      to: validDateInput(params.get('to')),
      collector: params.get('collector') ?? '',
      status: parsedStatus.success ? parsedStatus.data : '',
    },
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
  if (page > 1) params.set('page', String(page))

  const search = params.toString()
  const url = `${window.location.pathname}${search ? `?${search}` : ''}`
  if (replace) {
    window.history.replaceState(null, '', url)
  } else {
    window.history.pushState(null, '', url)
  }
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

export function MonitoringPage() {
  const queryClient = useQueryClient()
  const [urlState, setUrlState] = useState(readUrlState)
  const [selectedRun, setSelectedRun] = useState<SelectedRun | null>(null)
  const [initialQueriesSettled, setInitialQueriesSettled] = useState(false)
  const isFetching = useIsFetching({ queryKey: ['monitoring'] }) > 0

  useEffect(() => {
    const onPopState = () => setUrlState(readUrlState())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const runConditions = useMemo(
    () => ({
      collectorId: urlState.filters.collector || undefined,
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
  const freshnessQuery = useQuery(monitoringQueries.freshness({}))
  const runsQuery = useQuery(monitoringQueries.runs(runConditions))
  const detailConditions = selectedRun ?? { collectorId: '', runId: '' }
  const detailQuery = useQuery({
    ...monitoringQueries.runDetail(detailConditions),
    enabled: selectedRun !== null,
  })

  const primaryQueries = [
    summaryQuery,
    collectorsQuery,
    freshnessQuery,
    runsQuery,
  ]
  const allPrimaryQueriesSettled = primaryQueries.every(
    (query) => !query.isPending,
  )
  const initialLoading =
    !initialQueriesSettled && !allPrimaryQueriesSettled
  const allFailed = primaryQueries.every((query) => query.isError)
  const sourceErrors = collectSourceErrors(primaryQueries)
  const failedAreas = [
    summaryQuery.isError ? '전체 현황' : null,
    collectorsQuery.isError ? '수집기 현황' : null,
    freshnessQuery.isError ? '데이터 신선도' : null,
    runsQuery.isError ? '실행 이력' : null,
  ].filter((area): area is string => area !== null)
  const allEmpty =
    !primaryQueries.some((query) => query.isError) &&
    sourceErrors.length === 0 &&
    (summaryQuery.data?.items.length ?? 0) === 0 &&
    (collectorsQuery.data?.items.length ?? 0) === 0 &&
    (freshnessQuery.data?.items.length ?? 0) === 0 &&
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
    commitUrlState({ filters, page: 1 })
  }

  function changePage(page: number) {
    commitUrlState({
      ...urlState,
      page: Math.max(1, Math.min(page, MAX_RUNS_PAGE)),
    })
  }

  function selectRun(run: CollectorRun) {
    setSelectedRun({ collectorId: run.collector_id, runId: run.run_id })
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
      ) : allFailed ? (
        <MonitoringError onRetry={refresh} />
      ) : allEmpty ? (
        <MonitoringEmpty />
      ) : (
        <div className="space-y-6">
          <MonitoringPartialAlert errors={sourceErrors} failedAreas={failedAreas} />

          <KpiCards runs={summaryQuery.data?.items ?? []} />

          <section aria-label="수집기 현황" className="space-y-3">
            <div>
              <h2 className="text-lg font-semibold">수집기 현황</h2>
              <p className="text-sm text-muted-foreground">
                수집기별 가장 최근 실행과 작업 결과입니다.
              </p>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              {(collectorsQuery.data?.items ?? []).map((run) => (
                <CollectorCard
                  key={`${run.collector_id}:${run.run_id}`}
                  run={run}
                />
              ))}
            </div>
          </section>

          <FreshnessSummary items={freshnessQuery.data?.items ?? []} />

          <RunsTable
            runs={runsQuery.data?.items ?? []}
            total={runsQuery.data?.total ?? 0}
            collectors={collectorIds}
            filters={urlState.filters}
            page={urlState.page}
            onFiltersChange={changeFilters}
            onPageChange={changePage}
            onSelectRun={selectRun}
          />
        </div>
      )}

      <RunDetailSheet
        open={selectedRun !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedRun(null)
        }}
        run={detailQuery.data?.items[0]}
        isLoading={detailQuery.isPending && selectedRun !== null}
        error={
          detailQuery.error ??
          (detailQuery.data?.errors.length ? detailQuery.data.errors : undefined)
        }
      />
    </AppLayout>
  )
}
