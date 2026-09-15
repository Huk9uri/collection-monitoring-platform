import { Fragment } from 'react'
import { ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon } from 'lucide-react'

import { Button } from '../../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../../components/ui/table'
import type { CollectorRun, MonitoringStatus } from '../data/schema'
import { formatCount } from '../data/format-count'
import { collectorDisplayName } from './collector-card'
import { RunDetailDropdown } from './run-detail-dropdown'
import {
  formatSeoulDateTime,
  StatusBadge,
  statusPresentation,
} from './monitoring-state'

export const RUNS_PAGE_SIZE = 20
export const MAX_RUNS_PAGE = Math.floor(10_000 / RUNS_PAGE_SIZE) + 1

export interface RunFilters {
  from: string
  to: string
  brand?: string
  collector: string
  status: MonitoringStatus | ''
}

export interface RunFilterErrors {
  from?: string
  to?: string
}

interface RunsTableProps {
  runs: CollectorRun[]
  total: number
  collectors: string[]
  filters: RunFilters
  filterErrors: RunFilterErrors
  page: number
  onFiltersChange: (filters: RunFilters) => void
  onPageChange: (page: number) => void
  onSelectRun: (run: CollectorRun) => void
  selectedCollectorId?: string
  selectedRunId?: string
  detailRun?: CollectorRun
  isDetailLoading?: boolean
  detailError?: unknown
}

const statuses = Object.entries(statusPresentation) as [
  MonitoringStatus,
  (typeof statusPresentation)[MonitoringStatus],
][]

const fieldClassName =
  'h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-auto'

export function RunsTable({
  runs,
  total,
  collectors,
  filters,
  filterErrors,
  page,
  onFiltersChange,
  onPageChange,
  onSelectRun,
  selectedCollectorId,
  selectedRunId,
  detailRun,
  isDetailLoading = false,
  detailError,
}: RunsTableProps) {
  const totalPages = Math.min(
    MAX_RUNS_PAGE,
    Math.max(1, Math.ceil(total / RUNS_PAGE_SIZE)),
  )

  function updateFilter<Key extends keyof RunFilters>(key: Key, value: RunFilters[Key]) {
    onFiltersChange({ ...filters, [key]: value })
  }

  return (
    <section aria-label="실행 이력">
      <Card>
        <CardHeader className="gap-4">
          <div>
            <CardTitle>실행 이력</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              서버에서 기간과 수집기별 실행을 페이지 단위로 조회합니다.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" role="group" aria-label="실행 이력 필터">
            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              조회 시작일
              <input
                type="date"
                aria-label="조회 시작일"
                className={fieldClassName}
                value={filters.from}
                aria-invalid={filterErrors.from !== undefined}
                aria-describedby={filterErrors.from ? 'runs-from-error' : undefined}
                onChange={(event) => updateFilter('from', event.target.value)}
              />
              {filterErrors.from ? (
                <span id="runs-from-error" role="alert" className="text-destructive">
                  {filterErrors.from}
                </span>
              ) : null}
            </label>
            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              조회 종료일
              <input
                type="date"
                aria-label="조회 종료일"
                className={fieldClassName}
                value={filters.to}
                aria-invalid={filterErrors.to !== undefined}
                aria-describedby={filterErrors.to ? 'runs-to-error' : undefined}
                onChange={(event) => updateFilter('to', event.target.value)}
              />
              {filterErrors.to ? (
                <span id="runs-to-error" role="alert" className="text-destructive">
                  {filterErrors.to}
                </span>
              ) : null}
            </label>
            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              수집기 필터
              <select
                className={fieldClassName}
                value={filters.collector}
                onChange={(event) => updateFilter('collector', event.target.value)}
              >
                <option value="">전체 수집기</option>
                {collectors.map((collector) => (
                  <option key={collector} value={collector}>
                    {collectorDisplayName(collector)}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              브랜드 필터
              <select className={fieldClassName} value={filters.brand ?? ''}
                onChange={(event) => updateFilter('brand', event.target.value)}>
                <option value="">전체 브랜드</option>
                <option value="hanchon">한촌설렁탕</option>
                <option value="yuksoodang">육수당</option>
              </select>
            </label>
            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              상태 필터
              <select
                className={fieldClassName}
                value={filters.status}
                onChange={(event) =>
                  updateFilter('status', event.target.value as MonitoringStatus | '')
                }
              >
                <option value="">전체 상태</option>
                {statuses.map(([status, presentation]) => (
                  <option key={status} value={status}>
                    {presentation.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Table aria-label="수집 실행 이력">
            <TableHeader>
              <TableRow>
                <TableHead>실행 ID</TableHead>
                <TableHead>수집기</TableHead>
                <TableHead>브랜드</TableHead>
                <TableHead>상태</TableHead>
                <TableHead>시작</TableHead>
                <TableHead>원천</TableHead>
                <TableHead>신규</TableHead>
                <TableHead>변경</TableHead>
                <TableHead>실패 작업</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="h-24 text-center text-muted-foreground">
                    선택한 조건의 실행 이력이 없습니다.
                  </TableCell>
                </TableRow>
              ) : (
                runs.map((run) => {
                  const isExpanded =
                    selectedCollectorId === run.collector_id &&
                    selectedRunId === run.run_id
                  const detailId = `run-detail-${run.collector_id}-${run.run_id}`

                  return (
                    <Fragment key={`${run.collector_id}:${run.run_id}`}>
                      <TableRow data-state={isExpanded ? 'selected' : undefined}>
                    <TableCell>
                      <button
                        type="button"
                        className="font-medium text-primary underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        aria-label={`실행 ${run.run_id} 상세 보기`}
                        aria-expanded={isExpanded}
                        aria-controls={detailId}
                        onClick={() => onSelectRun(run)}
                      >
                        {run.run_id}
                        <ChevronDownIcon
                          aria-hidden="true"
                          className={`ml-1 inline size-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                        />
                      </button>
                    </TableCell>
                    <TableCell>{collectorDisplayName(run.collector_id)}</TableCell>
                    <TableCell>{run.scope_name ?? '-'}</TableCell>
                    <TableCell>
                      <StatusBadge status={run.status} />
                    </TableCell>
                    <TableCell>{formatSeoulDateTime(run.started_at)}</TableCell>
                    <TableCell>{formatCount(run.source_count)}</TableCell>
                    <TableCell>{formatCount(run.inserted_count)}</TableCell>
                    <TableCell>{formatCount(run.changed_count)}</TableCell>
                    <TableCell>{run.failed_units.toLocaleString('ko-KR')}</TableCell>
                      </TableRow>
                      {isExpanded ? (
                        <TableRow className="bg-muted/20 hover:bg-muted/20">
                          <TableCell colSpan={9} className="whitespace-normal p-3 sm:p-4">
                            <RunDetailDropdown
                              id={detailId}
                              run={detailRun}
                              isLoading={isDetailLoading}
                              error={detailError}
                            />
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </Fragment>
                  )
                })
              )}
            </TableBody>
          </Table>

          <div className="flex flex-col gap-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <p className="text-muted-foreground" aria-live="polite">
              총 {total.toLocaleString('ko-KR')}건 · {page}/{totalPages} 페이지
            </p>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-label="이전 페이지"
                disabled={page <= 1}
                onClick={() => onPageChange(page - 1)}
              >
                <ChevronLeftIcon aria-hidden="true" />
                이전
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-label="다음 페이지"
                disabled={page >= totalPages}
                onClick={() => onPageChange(page + 1)}
              >
                다음
                <ChevronRightIcon aria-hidden="true" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </section>
  )
}
