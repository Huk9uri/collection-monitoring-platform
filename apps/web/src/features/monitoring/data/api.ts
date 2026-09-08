import type { AxiosRequestConfig } from 'axios'
import type { z } from 'zod'

import { apiClient } from '../../../lib/api'
import {
  collectorsResponseSchema,
  freshnessResponseSchema,
  runDetailResponseSchema,
  runsResponseSchema,
  runsQueryConditionsSchema,
  summaryResponseSchema,
  type RunsQueryConditions,
} from './schema'

export type { RunsQueryConditions } from './schema'

export interface FreshnessQueryConditions {
  collectorId?: string
}

export interface RunDetailConditions {
  collectorId: string
  runId: string
}

async function getParsed<T>(
  path: string,
  schema: z.ZodType<T>,
  config?: AxiosRequestConfig,
): Promise<T> {
  const response = await apiClient.get<unknown>(path, config)
  return schema.parse(response.data)
}

export function getSummary() {
  return getParsed('/api/v1/monitoring/summary', summaryResponseSchema)
}

export function getCollectors() {
  return getParsed('/api/v1/monitoring/collectors', collectorsResponseSchema)
}

export async function getRuns(conditions: RunsQueryConditions) {
  const validated = runsQueryConditionsSchema.parse(conditions)

  return getParsed('/api/v1/monitoring/runs', runsResponseSchema, {
    params: {
      collector_id: validated.collectorId,
      started_from: validated.startedFrom,
      started_to: validated.startedTo,
      offset: validated.offset,
      page_size: validated.pageSize,
    },
  })
}

export function getRunDetail({ collectorId, runId }: RunDetailConditions) {
  return getParsed(
    `/api/v1/monitoring/runs/${encodeURIComponent(collectorId)}/${encodeURIComponent(runId)}`,
    runDetailResponseSchema,
  )
}

export function getFreshness(conditions: FreshnessQueryConditions) {
  return getParsed('/api/v1/monitoring/freshness', freshnessResponseSchema, {
    params: {
      collector_id: conditions.collectorId,
    },
  })
}
