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

const MAX_RUN_RANGE_MILLISECONDS = 93 * 24 * 60 * 60 * 1_000

export const runsQueryConditionsSchema = z
  .object({
    collectorId: z.string().optional(),
    startedFrom: utcDateTimeSchema.optional(),
    startedTo: utcDateTimeSchema.optional(),
    status: monitoringStatusSchema.optional(),
    offset: z.number().int().min(0).max(10_000).optional(),
    pageSize: z.number().int().min(1).max(100).optional(),
  })
  .superRefine(({ startedFrom, startedTo }, context) => {
    if (startedFrom === undefined || startedTo === undefined) {
      return
    }

    const range = Date.parse(startedTo) - Date.parse(startedFrom)
    if (range < 0) {
      context.addIssue({
        code: 'custom',
        message: '조회 종료 시각은 시작 시각보다 빠를 수 없습니다.',
        path: ['startedTo'],
      })
    } else if (range > MAX_RUN_RANGE_MILLISECONDS) {
      context.addIssue({
        code: 'custom',
        message: '조회 기간은 최대 93일입니다.',
        path: ['startedTo'],
      })
    }
  })

export const runDetailConditionsSchema = z.object({
  collectorId: z.string().min(1),
  runId: z.uuid(),
})

export const collectorAttemptSchema = z.object({
  unit_id: z.string(),
  unit_name: z.string(),
  attempt_no: z.number().int(),
  started_at: utcDateTimeSchema,
  completed_at: utcDateTimeSchema.nullable(),
  outcome: monitoringStatusSchema,
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
  run_id: z.uuid(),
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
  last_successful_check_at: utcDateTimeSchema.nullable(),
  latest_data_at: utcDateTimeSchema.nullable(),
  freshness_sla_minutes: z.number().int().positive().nullable(),
  freshness_overdue: z.boolean(),
})

export const collectorSummarySchema = z.object({
  collector_id: z.string(),
  display_name: z.string(),
  status: monitoringStatusSchema,
  latest_run: collectorRunSchema.nullable(),
  schedule_timezone: z.string().nullable(),
  daily_scheduled_time: z.string().nullable(),
  max_duration_minutes: z.number().int().positive().nullable(),
  last_successful_check_at: utcDateTimeSchema.nullable(),
  latest_data_at: utcDateTimeSchema.nullable(),
  freshness_overdue: z.boolean(),
  freshness: z.array(freshnessRecordSchema),
})

export const sourceErrorSchema = z.object({
  collector_id: z.string(),
  code: z.literal('SOURCE_UNAVAILABLE'),
  message: z.string(),
})

export const sourceStatusSchema = z.object({
  registered: z.number().int().min(0),
  succeeded: z.number().int().min(0),
  failed: z.number().int().min(0),
  all_sources_unavailable: z.boolean(),
})

const serviceResponseSchema = <T extends z.ZodType>(itemSchema: T) =>
  z.object({
    items: z.array(itemSchema),
    errors: z.array(sourceErrorSchema),
    source_status: sourceStatusSchema,
  })

export const summaryResponseSchema = z.object({
  overall_status: monitoringStatusSchema,
  registered_collectors: z.number().int().min(0),
  today_success_runs: z.number().int().min(0),
  today_incident_runs: z.number().int().min(0),
  running_runs: z.number().int().min(0),
  errors: z.array(sourceErrorSchema),
  source_status: sourceStatusSchema,
})
export const collectorsResponseSchema = serviceResponseSchema(
  collectorSummarySchema,
)
export const runDetailResponseSchema = serviceResponseSchema(collectorRunSchema)
export const freshnessResponseSchema = serviceResponseSchema(freshnessRecordSchema)

export const runsResponseSchema = z.object({
  items: z.array(collectorRunSchema),
  errors: z.array(sourceErrorSchema),
  source_status: sourceStatusSchema,
  total: z.number().int(),
})

export type MonitoringStatus = z.infer<typeof monitoringStatusSchema>
export type RunsQueryConditions = z.input<typeof runsQueryConditionsSchema>
export type RunDetailConditions = z.input<typeof runDetailConditionsSchema>
export type CollectorAttempt = z.infer<typeof collectorAttemptSchema>
export type CollectorRun = z.infer<typeof collectorRunSchema>
export type CollectorSummary = z.infer<typeof collectorSummarySchema>
export type FreshnessRecord = z.infer<typeof freshnessRecordSchema>
export type SourceError = z.infer<typeof sourceErrorSchema>
export type SourceStatus = z.infer<typeof sourceStatusSchema>
export type SummaryResponse = z.infer<typeof summaryResponseSchema>
export type CollectorsResponse = z.infer<typeof collectorsResponseSchema>
export type RunDetailResponse = z.infer<typeof runDetailResponseSchema>
export type FreshnessResponse = z.infer<typeof freshnessResponseSchema>
export type RunsResponse = z.infer<typeof runsResponseSchema>
