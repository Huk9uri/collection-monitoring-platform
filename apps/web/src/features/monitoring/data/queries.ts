import { queryOptions } from '@tanstack/react-query'

import {
  getCollectors,
  getRunDetail,
  getRuns,
  getSummary,
  type RunDetailConditions,
  type RunsQueryConditions,
} from './api'

const manualRefreshOnly = {
  staleTime: Number.POSITIVE_INFINITY,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  refetchOnMount: false,
} as const

export const monitoringQueries = {
  summary: () =>
    queryOptions({
      queryKey: ['monitoring', 'summary', {}] as const,
      queryFn: getSummary,
      ...manualRefreshOnly,
    }),
  collectors: () =>
    queryOptions({
      queryKey: ['monitoring', 'collectors', {}] as const,
      queryFn: getCollectors,
      ...manualRefreshOnly,
    }),
  runs: (conditions: RunsQueryConditions) =>
    queryOptions({
      queryKey: ['monitoring', 'runs', conditions] as const,
      queryFn: () => getRuns(conditions),
      ...manualRefreshOnly,
    }),
  runDetail: (conditions: RunDetailConditions) =>
    queryOptions({
      queryKey: ['monitoring', 'run-detail', conditions] as const,
      queryFn: () => getRunDetail(conditions),
      ...manualRefreshOnly,
    }),
}
