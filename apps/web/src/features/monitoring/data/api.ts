import type { AxiosRequestConfig } from 'axios'
import type { z } from 'zod'

import { apiClient } from '../../../lib/api'
import {
  collectorsResponseSchema,
  freshnessResponseSchema,
  runDetailResponseSchema,
  runDetailConditionsSchema,
  runsResponseSchema,
  runsQueryConditionsSchema,
  summaryResponseSchema,
  type RunDetailConditions,
  type RunsQueryConditions,
} from './schema'

export type { RunDetailConditions, RunsQueryConditions } from './schema'

export interface FreshnessQueryConditions {
  collectorId?: string
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
      ...(validated.scopeId ? { scope_id: validated.scopeId } : {}),
      started_from: validated.startedFrom,
      started_to: validated.startedTo,
      status: validated.status,
      offset: validated.offset,
      page_size: validated.pageSize,
    },
  })
}

export async function getRunDetail({ collectorId, runId }: RunDetailConditions) {
  const validated = runDetailConditionsSchema.parse({ collectorId, runId })

  return await getParsed(
    `/api/v1/monitoring/runs/${encodeURIComponent(validated.collectorId)}/${encodeURIComponent(validated.runId)}`,
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
