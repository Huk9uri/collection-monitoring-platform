import { AlertTriangleIcon, DatabaseIcon } from 'lucide-react'
import type { ComponentProps } from 'react'

import { Badge } from '../../../components/ui/badge'
import { Button } from '../../../components/ui/button'
import { Card, CardContent } from '../../../components/ui/card'
import { Skeleton } from '../../../components/ui/skeleton'
import type { MonitoringStatus, SourceError } from '../data/schema'

type StatusSeverity = 'healthy' | 'warning' | 'incident' | 'unknown'

interface StatusPresentation {
  label: string
  severity: StatusSeverity
  variant: ComponentProps<typeof Badge>['variant']
}

export const statusPresentation: Record<MonitoringStatus, StatusPresentation> = {
  SUCCESS: { label: '정상', severity: 'healthy', variant: 'healthy' },
  SUCCESS_EMPTY: {
    label: '데이터 없음',
    severity: 'healthy',
    variant: 'healthy',
  },
  WARNING: { label: '주의', severity: 'warning', variant: 'warning' },
  PARTIAL_FAILED: {
    label: '부분 실패',
    severity: 'incident',
    variant: 'incident',
  },
  FAILED: { label: '실패', severity: 'incident', variant: 'incident' },
  RUNNING: { label: '실행 중', severity: 'unknown', variant: 'outline' },
  ABORTED: { label: '중단', severity: 'incident', variant: 'incident' },
  NOT_RUN: { label: '미실행', severity: 'unknown', variant: 'outline' },
}

const seoulDateTimeFormatter = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

export function formatSeoulDateTime(value: string | null) {
  if (value === null) {
    return '기록 없음'
  }

  return seoulDateTimeFormatter.format(new Date(value))
}

export function StatusBadge({ status }: { status: MonitoringStatus }) {
  const presentation = statusPresentation[status]

  return (
    <Badge variant={presentation.variant} data-severity={presentation.severity}>
      {presentation.label}
    </Badge>
  )
}

export function MonitoringLoading() {
  return (
    <div
      role="status"
      aria-label="모니터링 데이터를 불러오는 중입니다."
      className="space-y-6"
    >
      <span className="sr-only">모니터링 데이터를 불러오는 중입니다.</span>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-hidden="true">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-32" />
        ))}
      </div>
      <Skeleton className="h-72" aria-hidden="true" />
    </div>
  )
}

export function MonitoringEmpty() {
  return (
    <Card>
      <CardContent
        role="status"
        aria-label="표시할 모니터링 데이터가 없습니다."
        className="flex min-h-72 flex-col items-center justify-center gap-3 text-center"
      >
        <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <DatabaseIcon aria-hidden="true" />
        </span>
        <div>
          <p className="font-semibold">표시할 모니터링 데이터가 없습니다.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            수집기가 실행되면 최신 상태와 이력이 여기에 표시됩니다.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

export function MonitoringError({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent
        role="alert"
        className="flex min-h-72 flex-col items-center justify-center gap-4 text-center"
      >
        <span className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertTriangleIcon aria-hidden="true" />
        </span>
        <div>
          <p className="font-semibold">모니터링 데이터를 불러오지 못했습니다.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            연결 상태를 확인한 뒤 다시 시도해 주세요.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={onRetry}>
          다시 시도
        </Button>
      </CardContent>
    </Card>
  )
}

interface MonitoringPartialAlertProps {
  errors: SourceError[]
  failedAreas?: string[]
}

function collectorName(collectorId: string) {
  if (collectorId === 'fcdaum') return 'FC다움'
  if (collectorId === 'hmr') return 'HMR'
  return collectorId
}

export function MonitoringPartialAlert({
  errors,
  failedAreas = [],
}: MonitoringPartialAlertProps) {
  if (errors.length === 0 && failedAreas.length === 0) {
    return null
  }

  const uniqueErrors = Array.from(
    new Map(
      errors.map((error) => [
        `${error.collector_id}:${error.message}`,
        error,
      ]),
    ).values(),
  )

  return (
    <div
      role="alert"
      className="flex gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm"
    >
      <AlertTriangleIcon
        className="mt-0.5 size-5 shrink-0 text-warning"
        aria-hidden="true"
      />
      <div>
        <p className="font-semibold">일부 데이터를 불러오지 못했습니다.</p>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-muted-foreground">
          {uniqueErrors.map((error) => (
            <li key={`${error.collector_id}:${error.message}`}>
              {collectorName(error.collector_id)}: {error.message}
            </li>
          ))}
          {failedAreas.map((area) => (
            <li key={area}>{area} 영역을 조회할 수 없습니다.</li>
          ))}
        </ul>
      </div>
    </div>
  )
}
