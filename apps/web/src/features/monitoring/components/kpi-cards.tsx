import {
  ActivityIcon,
  CheckCircle2Icon,
  CircleAlertIcon,
  LoaderCircleIcon,
} from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import type { CollectorRun } from '../data/schema'

const incidentStatuses = new Set(['PARTIAL_FAILED', 'FAILED', 'ABORTED'])
const healthyStatuses = new Set(['SUCCESS', 'SUCCESS_EMPTY'])

export function KpiCards({ runs }: { runs: CollectorRun[] }) {
  const values = [
    {
      label: '전체 수집기',
      value: runs.length,
      icon: ActivityIcon,
      tone: 'text-primary bg-primary/10',
    },
    {
      label: '정상',
      value: runs.filter((run) => healthyStatuses.has(run.status)).length,
      icon: CheckCircle2Icon,
      tone: 'text-positive bg-positive/10',
    },
    {
      label: '장애',
      value: runs.filter((run) => incidentStatuses.has(run.status)).length,
      icon: CircleAlertIcon,
      tone: 'text-destructive bg-destructive/10',
    },
    {
      label: '실행 중',
      value: runs.filter((run) => run.status === 'RUNNING').length,
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
