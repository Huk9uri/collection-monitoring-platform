import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import type { CollectorSummary } from '../data/schema'
import { formatCount } from '../data/format-count'
import { formatSeoulDateTime, StatusBadge } from './monitoring-state'

export function collectorDisplayName(collectorId: string) {
  if (collectorId === 'fcdaum') return 'FC다움'
  if (collectorId === 'hmr') return 'HMR'
  return collectorId
}

export function CollectorCard({ summary }: { summary: CollectorSummary }) {
  const run = summary.latest_run
  const name = summary.display_name

  return (
    <Card role="article" aria-label={`${name} 최신 상태`}>
      <CardHeader className="grid-cols-[1fr_auto] items-start">
        <div>
          <CardTitle>{name}</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            {run === null
              ? '실행 이력 없음'
              : `${formatSeoulDateTime(run.started_at)} 시작`}
          </p>
        </div>
        <StatusBadge status={summary.status} />
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-md bg-muted/60 p-3">
            <dt className="text-muted-foreground">성공 작업</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums">
              {(run?.successful_units ?? 0).toLocaleString('ko-KR')}
            </dd>
          </div>
          <div className="rounded-md bg-muted/60 p-3">
            <dt className="text-muted-foreground">실패 작업</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums">
              {(run?.failed_units ?? 0).toLocaleString('ko-KR')}
            </dd>
          </div>
          <div className="col-span-2 flex items-center justify-between border-t pt-3">
            <dt className="text-muted-foreground">신규 / 변경 / 동일</dt>
            <dd className="font-medium tabular-nums">
              {formatCount(run?.inserted_count ?? null)} /{' '}
              {formatCount(run?.changed_count ?? null)} /{' '}
              {formatCount(run?.unchanged_count ?? null)}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  )
}
