import { z } from 'zod'

export const monitoringStatusSchema = z.enum([
  'SUCCESS',
  'SUCCESS_EMPTY',
  'WARNING',
  'PARTIAL_FAILED',
  'FAILED',
  'RUNNING',
  'ABORTED',
  'NOT_RUN',
])

export const utcDateTimeSchema = z
  .iso.datetime({ offset: true })
  .refine((value) => /(?:Z|\+00:00)$/i.test(value), {
    message: 'UTC ISO 8601 시각이어야 합니다.',
  })

export const collectorAttemptSchema = z.object({
  unit_id: z.string(),
  unit_name: z.string(),
  attempt_no: z.number().int(),
  started_at: utcDateTimeSchema,
  completed_at: utcDateTimeSchema.nullable(),
  raw_status: z.string(),
  source_count: z.number().int(),
  inserted_count: z.number().int(),
  changed_count: z.number().int(),
  unchanged_count: z.number().int(),
  committed: z.boolean().nullable(),
  error_category: z.string().nullable(),
})

export const collectorRunSchema = z.object({
  collector_id: z.string(),
  run_id: z.string(),
  scheduled_date: z.iso.date(),
  started_at: utcDateTimeSchema,
  completed_at: utcDateTimeSchema.nullable(),
  status: monitoringStatusSchema,
  successful_units: z.number().int(),
  failed_units: z.number().int(),
  source_count: z.number().int(),
  inserted_count: z.number().int(),
  changed_count: z.number().int(),
  unchanged_count: z.number().int(),
  attempts: z.array(collectorAttemptSchema),
})

export const freshnessRecordSchema = z.object({
  collector_id: z.string(),
  dataset_id: z.string(),
  latest_at: utcDateTimeSchema.nullable(),
})

export const sourceErrorSchema = z.object({
  collector_id: z.string(),
  code: z.literal('SOURCE_UNAVAILABLE'),
  message: z.string(),
})

const serviceResponseSchema = <T extends z.ZodType>(itemSchema: T) =>
  z.object({
    items: z.array(itemSchema),
    errors: z.array(sourceErrorSchema),
  })

export const summaryResponseSchema = serviceResponseSchema(collectorRunSchema)
export const collectorsResponseSchema = serviceResponseSchema(collectorRunSchema)
export const runDetailResponseSchema = serviceResponseSchema(collectorRunSchema)
export const freshnessResponseSchema = serviceResponseSchema(freshnessRecordSchema)

export const runsResponseSchema = z.object({
  items: z.array(collectorRunSchema),
  errors: z.array(sourceErrorSchema),
  total: z.number().int(),
})

export type MonitoringStatus = z.infer<typeof monitoringStatusSchema>
export type CollectorAttempt = z.infer<typeof collectorAttemptSchema>
export type CollectorRun = z.infer<typeof collectorRunSchema>
export type FreshnessRecord = z.infer<typeof freshnessRecordSchema>
export type SourceError = z.infer<typeof sourceErrorSchema>
export type SummaryResponse = z.infer<typeof summaryResponseSchema>
export type CollectorsResponse = z.infer<typeof collectorsResponseSchema>
export type RunDetailResponse = z.infer<typeof runDetailResponseSchema>
export type FreshnessResponse = z.infer<typeof freshnessResponseSchema>
export type RunsResponse = z.infer<typeof runsResponseSchema>
