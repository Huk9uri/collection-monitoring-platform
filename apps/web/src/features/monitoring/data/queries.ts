import { queryOptions } from '@tanstack/react-query'

import {
  getCollectors,
  getFreshness,
  getRunDetail,
  getRuns,
  getSummary,
  type FreshnessQueryConditions,
  type RunDetailConditions,
  type RunsQueryConditions,
} from './api'

export const monitoringQueries = {
  summary: () =>
    queryOptions({
      queryKey: ['monitoring', 'summary', {}] as const,
      queryFn: getSummary,
    }),
  collectors: () =>
    queryOptions({
      queryKey: ['monitoring', 'collectors', {}] as const,
      queryFn: getCollectors,
    }),
  runs: (conditions: RunsQueryConditions) =>
    queryOptions({
      queryKey: ['monitoring', 'runs', conditions] as const,
      queryFn: () => getRuns(conditions),
    }),
  runDetail: (conditions: RunDetailConditions) =>
    queryOptions({
      queryKey: ['monitoring', 'run-detail', conditions] as const,
      queryFn: () => getRunDetail(conditions),
    }),
  freshness: (conditions: FreshnessQueryConditions) =>
    queryOptions({
      queryKey: ['monitoring', 'freshness', conditions] as const,
      queryFn: () => getFreshness(conditions),
    }),
}
