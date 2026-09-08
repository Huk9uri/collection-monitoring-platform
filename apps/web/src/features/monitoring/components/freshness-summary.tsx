import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import { Badge } from '../../../components/ui/badge'
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
            마지막 성공 확인과 실제 데이터 변경 시각을 구분해 표시합니다.
          </p>
        </CardHeader>
        <CardContent>
          <Table aria-label="데이터 신선도">
            <TableHeader>
              <TableRow>
                <TableHead>수집기</TableHead>
                <TableHead>데이터셋</TableHead>
                <TableHead>마지막 성공 확인</TableHead>
                <TableHead>최신 데이터 시각</TableHead>
                <TableHead>신선도 SLA</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
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
                      {item.last_successful_check_at === null
                        ? '성공 확인 없음'
                        : formatSeoulDateTime(item.last_successful_check_at)}
                    </TableCell>
                    <TableCell>
                      {item.latest_data_at === null
                        ? '수집 이력 없음'
                        : formatSeoulDateTime(item.latest_data_at)}
                    </TableCell>
                    <TableCell>
                      {item.freshness_overdue ? (
                        <Badge variant="warning">SLA 초과</Badge>
                      ) : item.freshness_sla_minutes === null ? (
                        '정책 없음'
                      ) : (
                        `${item.freshness_sla_minutes.toLocaleString('ko-KR')}분 이내`
                      )}
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
