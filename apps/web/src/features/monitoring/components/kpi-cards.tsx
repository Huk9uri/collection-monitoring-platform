import {
  ActivityIcon,
  AlertTriangleIcon,
  CheckCircle2Icon,
  CircleAlertIcon,
  CircleMinusIcon,
  LoaderCircleIcon,
} from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import type { CollectorSummary } from '../data/schema'
import { statusPresentation } from './monitoring-state'

interface CollectorStatusCounts {
  total: number
  healthy: number
  warning: number
  incident: number
  running: number
  notRun: number
}

export function countCollectorStatuses(
  collectors: CollectorSummary[],
): CollectorStatusCounts {
  return collectors.reduce<CollectorStatusCounts>(
    (counts, collector) => {
      counts.total += 1
      const severity = statusPresentation[collector.status].severity

      if (severity === 'healthy') counts.healthy += 1
      if (severity === 'warning') counts.warning += 1
      if (severity === 'incident') counts.incident += 1
      if (collector.status === 'RUNNING') counts.running += 1
      if (collector.status === 'NOT_RUN') counts.notRun += 1

      return counts
    },
    {
      total: 0,
      healthy: 0,
      warning: 0,
      incident: 0,
      running: 0,
      notRun: 0,
    },
  )
}

export function KpiCards({ collectors = [] }: { collectors?: CollectorSummary[] }) {
  const counts = countCollectorStatuses(collectors)
  const values = [
    {
      label: '전체 수집기',
      value: counts.total,
      icon: ActivityIcon,
      tone: 'text-primary bg-primary/10',
    },
    {
      label: '정상',
      value: counts.healthy,
      icon: CheckCircle2Icon,
      tone: 'text-positive-foreground bg-positive-surface',
    },
    {
      label: '주의',
      value: counts.warning,
      icon: AlertTriangleIcon,
      tone: 'text-warning-foreground bg-warning-surface',
    },
    {
      label: '장애',
      value: counts.incident,
      icon: CircleAlertIcon,
      tone: 'text-destructive bg-destructive/10',
    },
    {
      label: '실행 중',
      value: counts.running,
      icon: LoaderCircleIcon,
      tone: 'text-muted-foreground bg-muted',
    },
    {
      label: '미실행',
      value: counts.notRun,
      icon: CircleMinusIcon,
      tone: 'text-muted-foreground bg-muted',
    },
  ]

  return (
    <section aria-label="수집기 상태 요약" className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">전체 현황</h2>
        <p className="text-sm text-muted-foreground">
          수집기별 가장 최근 실행 상태
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {values.map(({ label, value, icon: Icon, tone }) => (
          <Card key={label} className="gap-3 py-5">
            <CardHeader className="grid-cols-[1fr_auto] items-center">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {label}
              </CardTitle>
              <span className={`flex size-9 items-center justify-center rounded-lg ${tone}`}>
                <Icon className="size-4" aria-hidden="true" />
              </span>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-semibold tabular-nums">{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  )
}
