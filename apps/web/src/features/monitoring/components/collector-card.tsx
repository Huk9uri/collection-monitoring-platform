import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import type { CollectorRun } from '../data/schema'
import { formatSeoulDateTime, StatusBadge } from './monitoring-state'

export function collectorDisplayName(collectorId: string) {
  if (collectorId === 'fcdaum') return 'FC다움'
  if (collectorId === 'hmr') return 'HMR'
  return collectorId
}

export function CollectorCard({ run }: { run: CollectorRun }) {
  const name = collectorDisplayName(run.collector_id)

  return (
    <Card role="article" aria-label={`${name} 최신 상태`}>
      <CardHeader className="grid-cols-[1fr_auto] items-start">
        <div>
          <CardTitle>{name}</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            {formatSeoulDateTime(run.started_at)} 시작
          </p>
        </div>
        <StatusBadge status={run.status} />
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-md bg-muted/60 p-3">
            <dt className="text-muted-foreground">성공 작업</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums">
              {run.successful_units.toLocaleString('ko-KR')}
            </dd>
          </div>
          <div className="rounded-md bg-muted/60 p-3">
            <dt className="text-muted-foreground">실패 작업</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums">
              {run.failed_units.toLocaleString('ko-KR')}
            </dd>
          </div>
          <div className="col-span-2 flex items-center justify-between border-t pt-3">
            <dt className="text-muted-foreground">신규 / 변경 / 동일</dt>
            <dd className="font-medium tabular-nums">
              {run.inserted_count.toLocaleString('ko-KR')} /{' '}
              {run.changed_count.toLocaleString('ko-KR')} /{' '}
              {run.unchanged_count.toLocaleString('ko-KR')}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  )
}
