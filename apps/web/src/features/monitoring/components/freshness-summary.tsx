import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../../components/ui/table'
import type { FreshnessRecord } from '../data/schema'
import { collectorDisplayName } from './collector-card'
import { formatSeoulDateTime } from './monitoring-state'

export function FreshnessSummary({ items }: { items: FreshnessRecord[] }) {
  return (
    <section aria-label="데이터 신선도">
      <Card>
        <CardHeader>
          <CardTitle>데이터 신선도</CardTitle>
          <p className="text-sm text-muted-foreground">
            원천 및 적재 데이터의 마지막 확인 시각입니다.
          </p>
        </CardHeader>
        <CardContent>
          <Table aria-label="데이터 신선도">
            <TableHeader>
              <TableRow>
                <TableHead>수집기</TableHead>
                <TableHead>데이터셋</TableHead>
                <TableHead>최신 데이터 시각</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} className="h-24 text-center text-muted-foreground">
                    신선도 정보가 없습니다.
                  </TableCell>
                </TableRow>
              ) : (
                items.map((item) => (
                  <TableRow key={`${item.collector_id}:${item.dataset_id}`}>
                    <TableCell className="font-medium">
                      {collectorDisplayName(item.collector_id)}
                    </TableCell>
                    <TableCell>{item.dataset_id}</TableCell>
                    <TableCell>
                      {item.latest_at === null
                        ? '수집 이력 없음'
                        : formatSeoulDateTime(item.latest_at)}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </section>
  )
}
