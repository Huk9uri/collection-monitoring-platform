import { collectorDisplayName } from './collector-card'
import { Badge } from '../../../components/ui/badge'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '../../../components/ui/sheet'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../../components/ui/table'
import type { CollectorAttempt, CollectorRun } from '../data/schema'
import { formatCount } from '../data/format-count'
import { formatSeoulDateTime, StatusBadge } from './monitoring-state'

interface RunDetailSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  run?: CollectorRun
  isLoading: boolean
  error?: unknown
}

function attemptOutcome(attempt: CollectorAttempt) {
  const status = attempt.outcome

  if (status === 'SUCCESS' || status === 'SUCCESS_EMPTY') {
    return { label: '성공', variant: 'healthy' as const }
  }
  if (status === 'PARTIAL_FAILED' || status === 'FAILED' || status === 'ABORTED') {
    return { label: '실패', variant: 'incident' as const }
  }
  if (status === 'RUNNING') {
    return { label: '실행 중', variant: 'outline' as const }
  }
  if (status === 'NOT_RUN') {
    return { label: '미실행', variant: 'outline' as const }
  }
  if (status === 'WARNING') {
    return { label: '주의', variant: 'warning' as const }
  }
  return { label: '상태 확인 필요', variant: 'warning' as const }
}

export function RunDetailSheet({
  open,
  onOpenChange,
  run,
  isLoading,
  error,
}: RunDetailSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader className="border-b pr-12">
          <SheetTitle>실행 상세</SheetTitle>
          <SheetDescription>
            수집 작업의 시도와 데이터 적재 결과입니다.
          </SheetDescription>
        </SheetHeader>

        {isLoading ? (
          <p className="px-4 text-sm text-muted-foreground" role="status">
            실행 상세를 불러오는 중입니다.
          </p>
        ) : error ? (
          <p className="px-4 text-sm text-destructive" role="alert">
            실행 상세를 불러오지 못했습니다.
          </p>
        ) : !run ? (
          <p className="px-4 text-sm text-muted-foreground">실행 정보가 없습니다.</p>
        ) : (
          <div className="space-y-6 px-4 pb-6">
            <dl className="grid grid-cols-2 gap-4 rounded-lg border bg-muted/30 p-4 text-sm">
              <div>
                <dt className="text-muted-foreground">실행 ID</dt>
                <dd className="mt-1 break-all font-medium">{run.run_id}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">{run.collector_id === 'naver-store-hours' ? '품질 상태' : '상태'}</dt>
                <dd className="mt-1">
                  <StatusBadge status={run.status} />
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">브랜드</dt>
                <dd className="mt-1 font-medium">{run.scope_name ?? '-'}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">시작</dt>
                <dd className="mt-1">{formatSeoulDateTime(run.started_at)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">완료</dt>
                <dd className="mt-1">{formatSeoulDateTime(run.completed_at)}</dd>
              </div>
              <div><dt className="text-muted-foreground">수집기</dt><dd>{collectorDisplayName(run.collector_id)}</dd></div>
              {run.collector_id === 'naver-store-hours' && <>
                {[
                  ['상위 실행 ID', run.parent_run_id ?? '-'],
                  ['원시 실행 결과', run.raw_status ?? '-'],
                  ['실행 유형', run.execution_kind === 'scheduled' ? '예약 실행' : run.execution_kind === 'preflight-only' ? '사전 점검 전용' : '-'],
                  ['대상 매장', formatCount(run.source_count)],
                  ['검토 매장', formatCount(run.review_count ?? null)],
                  ['실패 매장', formatCount(run.failure_count ?? null)],
                  ['확인 매장', formatCount(run.coverage_count ?? null)],
                  ['적용 매장', formatCount(run.applied_count ?? null)],
                  ['신규 확정 매장', formatCount(run.inserted_count)],
                  ['변경 확정 매장', formatCount(run.changed_count)],
                  ['동일 확정 매장', formatCount(run.unchanged_count)],
                  ['DB 반영', run.committed == null ? '-' : run.committed ? '반영 확인' : '미반영'],
                  ['성공 확인 시각', formatSeoulDateTime(run.successful_check_at ?? null)],
                  ['오류 분류', run.error_category ?? '-'],
                ].map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="mt-1 break-all">{value}</dd></div>)}
              </>}
            </dl>
            {run.collector_id === 'naver-store-hours' && <p className="text-sm text-muted-foreground">집계 단위는 요일 행 수가 아닌 매장 수입니다. 신규·변경·동일은 Apply 확정 결과이며 dry-run 예상 결과는 하위 시도에서 확인합니다.</p>}

            <section aria-labelledby="attempts-title" className="space-y-3">
              <h3 id="attempts-title" className="font-semibold">
                하위 작업 시도
              </h3>
              {run.attempts.some((attempt) => attempt.timing_basis === 'parent-window') && <p className="text-sm text-muted-foreground">예약 실행 관측 구간은 자식 실행의 시각 근거가 없는 과거 기록에 사용하며, 정확한 단계 소요시간이 아닙니다.</p>}
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>작업</TableHead>
                    <TableHead>시도</TableHead>
                    <TableHead>단계</TableHead>
                    <TableHead>시각 근거</TableHead>
                    <TableHead>하위 실행 ID</TableHead>
                    <TableHead>매장 코드</TableHead>
                    <TableHead>DB 반영</TableHead>
                    <TableHead>결과</TableHead>
                    <TableHead>원천</TableHead>
                    <TableHead>신규</TableHead>
                    <TableHead>변경</TableHead>
                    <TableHead>동일</TableHead>
                    <TableHead>오류 분류</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {run.attempts.map((attempt) => {
                    const outcome = attemptOutcome(attempt)

                    return (
                      <TableRow key={`${attempt.unit_id}-${attempt.attempt_no}`}>
                        <TableCell className="font-medium">
                          {attempt.unit_name}
                        </TableCell>
                        <TableCell>{attempt.attempt_no}</TableCell>
                        <TableCell>{attempt.stage === 'dry-run' ? 'dry-run (예상)' : attempt.stage ?? '-'}</TableCell>
                        <TableCell>{attempt.timing_basis === 'parent-window' ? '예약 실행 관측 구간' : attempt.timing_basis === 'worker-report' ? '자식 실행 보고 시각' : '-'}</TableCell>
                        <TableCell className="break-all">{attempt.child_run_id ?? '-'}</TableCell>
                        <TableCell>{attempt.store_codes?.join(', ') || '-'}</TableCell>
                        <TableCell>{attempt.committed === null ? '-' : attempt.committed ? (run.collector_id === 'naver-store-hours' ? '반영 확인' : '반영 완료') : '미반영'}</TableCell>
                        <TableCell>
                          <Badge variant={outcome.variant}>{outcome.label}</Badge>
                        </TableCell>
                        <TableCell>{formatCount(attempt.source_count)}</TableCell>
                        <TableCell>{formatCount(attempt.inserted_count)}</TableCell>
                        <TableCell>{formatCount(attempt.changed_count)}</TableCell>
                        <TableCell>{formatCount(attempt.unchanged_count)}</TableCell>
                        <TableCell>{attempt.error_category ?? '없음'}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </section>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
