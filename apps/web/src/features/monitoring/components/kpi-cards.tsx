import {
  ActivityIcon,
  CheckCircle2Icon,
  CircleAlertIcon,
  LoaderCircleIcon,
} from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import type { SummaryResponse } from '../data/schema'

export function KpiCards({ summary }: { summary?: SummaryResponse }) {
  const values = [
    {
      label: '전체 수집기',
      value: summary?.registered_collectors ?? 0,
      icon: ActivityIcon,
      tone: 'text-primary bg-primary/10',
    },
    {
      label: '오늘 정상',
      value: summary?.today_success_runs ?? 0,
      icon: CheckCircle2Icon,
      tone: 'text-positive-foreground bg-positive-surface',
    },
    {
      label: '오늘 장애',
      value: summary?.today_incident_runs ?? 0,
      icon: CircleAlertIcon,
      tone: 'text-destructive bg-destructive/10',
    },
    {
      label: '실행 중',
      value: summary?.running_runs ?? 0,
      icon: LoaderCircleIcon,
      tone: 'text-muted-foreground bg-muted',
    },
  ]

  return (
    <section aria-label="전체 현황" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
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
    </section>
  )
}
