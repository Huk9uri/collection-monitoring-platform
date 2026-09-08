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
import { formatSeoulDateTime, StatusBadge } from './monitoring-state'

interface RunDetailSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  run?: CollectorRun
  isLoading: boolean
  error?: unknown
}

function attemptOutcome(attempt: CollectorAttempt) {
  const status = attempt.raw_status.trim().toUpperCase()

  if (
    (status === 'SUCCESS' || status === 'SUCCESS_EMPTY') &&
    attempt.committed !== false
  ) {
    return { label: '성공', variant: 'healthy' as const }
  }
  if (
    attempt.committed === false ||
    /FAILED|FAILURE|ERROR|ABORTED/.test(status)
  ) {
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
                <dt className="text-muted-foreground">상태</dt>
                <dd className="mt-1">
                  <StatusBadge status={run.status} />
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">시작</dt>
                <dd className="mt-1">{formatSeoulDateTime(run.started_at)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">완료</dt>
                <dd className="mt-1">{formatSeoulDateTime(run.completed_at)}</dd>
              </div>
            </dl>

            <section aria-labelledby="attempts-title" className="space-y-3">
              <h3 id="attempts-title" className="font-semibold">
                하위 작업 시도
              </h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>작업</TableHead>
                    <TableHead>시도</TableHead>
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
                        <TableCell>
                          <Badge variant={outcome.variant}>{outcome.label}</Badge>
                        </TableCell>
                        <TableCell>{attempt.source_count.toLocaleString('ko-KR')}</TableCell>
                        <TableCell>{attempt.inserted_count.toLocaleString('ko-KR')}</TableCell>
                        <TableCell>{attempt.changed_count.toLocaleString('ko-KR')}</TableCell>
                        <TableCell>{attempt.unchanged_count.toLocaleString('ko-KR')}</TableCell>
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
