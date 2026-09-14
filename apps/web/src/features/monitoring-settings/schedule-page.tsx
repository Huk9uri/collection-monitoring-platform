import { useEffect, useState, type FormEvent } from 'react'
import { apiClient } from '../../lib/api'
import { Button } from '../../components/ui/button'
import * as Dialog from '@radix-ui/react-dialog'

interface Slot { weekday_number: number; scheduled_time: string; schedule_enabled: boolean }
interface Policy { timezone_name: string; max_duration_minutes: number | null; start_grace_minutes: number; schedule_attribution_window_minutes: number; monitoring_enabled: boolean; schedules: Slot[]; freshness: Record<string, number> }
interface RecordView { collector_id: string; policy: Policy | null; version: string | null; updated_at: string | null; policy_source: string; warning: string | null; dataset_ids: string[] }
interface History { history_id: string; collector_id: string; change_reason: string; changed_at: string; before: unknown; after: unknown }
const weekdays = ['월', '화', '수', '목', '금', '토', '일']
const inputClass = 'mt-1 block w-full rounded-md border bg-background p-2 text-sm disabled:opacity-70'

export function SchedulePage({ admin, onPolicySaved }: { admin: boolean; onPolicySaved?: () => void }) {
  const [items, setItems] = useState<RecordView[]>([])
  const [selected, select] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const [history, setHistory] = useState<History[]>([])
  useEffect(() => {
    let active = true
    apiClient.get<{ items: RecordView[] }>('/api/v1/settings/schedules').then(({ data }) => {
      if (active) { setItems(data.items); select(data.items[0]?.collector_id ?? '') }
    }).catch(() => { if (active) setError('기준 일정을 불러올 수 없습니다.') }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  const record = items.find(item => item.collector_id === selected)
  return <main className="mx-auto max-w-5xl space-y-6 p-6">
    <header><h1 className="text-2xl font-semibold">모니터링 기준 일정</h1><p className="mt-3 rounded-lg border bg-muted p-4 text-sm">이 설정은 대시보드의 상태 판정 기준만 변경하며 실제 수집기 실행 일정에는 영향을 주지 않습니다.</p></header>
    {loading && <p role="status">일정 조회 중…</p>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!loading && !error && !items.length && <p>등록된 수집기가 없습니다.</p>}
    {!!items.length && <label className="block max-w-sm text-sm">수집기<select className={inputClass} value={selected} onChange={event => select(event.target.value)}>{items.map(item => <option key={item.collector_id}>{item.collector_id}</option>)}</select></label>}
    {record && <ScheduleEditor key={`${record.collector_id}:${record.version}`} record={record} admin={admin} onSaved={updated => { setItems(items.map(item => item.collector_id === updated.collector_id ? { ...updated, dataset_ids: item.dataset_ids, policy_source: 'db', warning: null } : item)); setHistory([]); setNotice('기준 일정을 저장했습니다. 다음 조회부터 새 기준이 적용됩니다.'); onPolicySaved?.() }} />}
    {admin && <section className="space-y-3 border-t pt-5"><h2 className="text-lg font-semibold">변경 이력</h2><Button variant="outline" onClick={() => { void apiClient.get<{ items: History[] }>('/api/v1/settings/history').then(({ data }) => setHistory(data.items)).catch(() => setError('변경 이력을 불러올 수 없습니다.')) }}>최근 변경 50건 조회</Button>
      {history.map(item => <details key={item.history_id} className="rounded-md border p-3"><summary>{item.changed_at} · {item.collector_id} · {item.change_reason}</summary><div className="grid gap-3 overflow-auto p-3 sm:grid-cols-2"><pre className="text-xs">변경 전{JSON.stringify(item.before, null, 2)}</pre><pre className="text-xs">변경 후{JSON.stringify(item.after, null, 2)}</pre></div></details>)}
    </section>}
  </main>
}

function ScheduleEditor({ record, admin, onSaved }: { record: RecordView; admin: boolean; onSaved: (record: RecordView) => void }) {
  const [slots, setSlots] = useState<Slot[]>(record.policy?.schedules ?? [])
  const [enabled, setEnabled] = useState(record.policy?.monitoring_enabled ?? false)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<(Policy & { change_reason: string; version: string | null }) | null>(null)
  const [conflict, setConflict] = useState<RecordView | null>(null)
  const [version, setVersion] = useState(record.version)
  function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const freshness: Record<string, number> = {}
    for (const id of record.dataset_ids) { const value = form.get(`freshness:${id}`); if (value) freshness[id] = Number(value) }
    if (enabled && !slots.some(slot => slot.schedule_enabled)) { setMessage('활성 일정을 한 개 이상 추가하세요.'); return }
    if (!String(form.get('reason')).trim()) { setMessage('변경 사유를 입력하세요.'); return }
    setMessage('')
    setPending({ timezone_name: String(form.get('zone')), max_duration_minutes: form.get('duration') ? Number(form.get('duration')) : null,
      start_grace_minutes: Number(form.get('grace')), schedule_attribution_window_minutes: Number(form.get('window')),
      monitoring_enabled: enabled, schedules: slots, freshness, version, change_reason: String(form.get('reason')).trim() })
  }
  async function save() {
    setBusy(true)
    try {
      const { data } = await apiClient.put<RecordView>(`/api/v1/settings/schedules/${record.collector_id}`, pending)
      onSaved(data); setPending(null); setMessage('기준 일정을 저장했습니다.')
    } catch (err) {
      const response = (err as { response?: { status?: number; data?: { latest?: RecordView } } }).response
      if (response?.status === 409 && response.data?.latest) { setConflict(response.data.latest); setPending(null); setMessage('다른 관리자가 설정을 변경했습니다. 입력은 보존되었습니다. 최신 정책을 비교하세요.') }
      else { setPending(null); setMessage('저장하지 못했습니다. 입력과 세션·서버 상태를 확인하세요.') }
    } finally { setBusy(false) }
  }
  return <section className="space-y-4 rounded-xl border bg-card p-5">
    <div className="text-sm text-muted-foreground">설정 출처: {record.policy_source} · 변경 시각: {record.updated_at ?? 'DB 저장 전'}</div>
    {record.warning && <p role="alert">{record.warning}</p>}
    {message && <p role="status" className="rounded-md bg-muted p-3">{message}</p>}
    {!record.policy && <p>저장된 기준 일정이 없습니다. {admin ? '실제 운영 기준을 입력하세요.' : '관리자에게 설정을 요청하세요.'}</p>}
    <form onSubmit={prepare} className="space-y-5">
      <fieldset disabled={!admin || busy} className="space-y-5">
        <legend className="mb-3 font-medium">{admin ? '기준 일정 편집' : '기준 일정 조회'}</legend>
        <label className="flex items-center gap-2"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} />일정 기반 판정 활성화</label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm">시간대<input name="zone" className={inputClass} required defaultValue={record.policy?.timezone_name ?? ''} placeholder="Asia/Seoul" /></label>
          <label className="text-sm">최대 실행시간 (분, 선택)<input name="duration" className={inputClass} type="number" min={1} defaultValue={record.policy?.max_duration_minutes ?? ''} /></label>
          <label className="text-sm">시작 유예 (분)<input name="grace" className={inputClass} required type="number" min={1} defaultValue={record.policy?.start_grace_minutes ?? ''} /></label>
          <label className="text-sm">예정 회차 귀속 범위 (분)<input name="window" className={inputClass} required type="number" min={1} defaultValue={record.policy?.schedule_attribution_window_minutes ?? ''} /></label>
        </div>
        <div className="space-y-2"><h2 className="font-medium">실행 요일·시각</h2>
          {slots.map((slot, index) => <div key={index} className="flex flex-wrap items-center gap-3 rounded-md border p-3">
            <label>요일<select aria-label={`${index + 1}번째 요일`} value={slot.weekday_number} className={inputClass} onChange={event => setSlots(slots.map((s, i) => i === index ? { ...s, weekday_number: Number(event.target.value) } : s))}>{weekdays.map((day, i) => <option key={day} value={i + 1}>{day}</option>)}</select></label>
            <label>시각<input aria-label={`${index + 1}번째 시각`} type="time" step={1} required className={inputClass} value={slot.scheduled_time} onChange={event => setSlots(slots.map((s, i) => i === index ? { ...s, scheduled_time: event.target.value } : s))} /></label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={slot.schedule_enabled} onChange={event => setSlots(slots.map((s, i) => i === index ? { ...s, schedule_enabled: event.target.checked } : s))} />활성</label>
            {admin && <Button type="button" variant="ghost" aria-label={`${index + 1}번째 일정 삭제`} onClick={() => setSlots(slots.filter((_, i) => i !== index))}>삭제</Button>}
          </div>)}
          {admin && <Button type="button" variant="outline" onClick={() => setSlots([...slots, { weekday_number: 1, scheduled_time: '', schedule_enabled: true }])}>일정 추가</Button>}
        </div>
        {!!record.dataset_ids.length && <div className="grid gap-3 sm:grid-cols-2">{record.dataset_ids.map(id => <label key={id} className="text-sm">{id} 신선도 SLA (분, 선택)<input name={`freshness:${id}`} type="number" min={1} className={inputClass} defaultValue={record.policy?.freshness[id] ?? ''} /></label>)}</div>}
        {admin && <label className="block text-sm">변경 사유<textarea name="reason" required maxLength={1000} className={inputClass} /></label>}
      </fieldset>
      {admin && <Button disabled={busy || !!conflict}>저장 검토</Button>}
    </form>
    {conflict && <div className="space-y-3 rounded-md border p-4"><h2 className="font-semibold">최신 정책 비교</h2><pre className="max-h-64 overflow-auto text-xs">{JSON.stringify(conflict.policy, null, 2)}</pre><p className="text-sm">위 최신 값과 현재 입력을 비교한 뒤 다시 저장하세요.</p><Button onClick={() => { setVersion(conflict.version); setConflict(null); setMessage('최신 버전을 확인했습니다. 필요한 입력을 조정한 뒤 저장 검토를 누르세요.') }}>비교 완료 · 현재 입력 유지</Button></div>}
    <Dialog.Root open={pending !== null} onOpenChange={open => { if (!open && !busy) setPending(null) }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 bg-foreground/30" /><Dialog.Content className="fixed left-1/2 top-1/2 w-[min(90vw,30rem)] -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-xl border bg-background p-6 shadow-lg"><Dialog.Title className="font-semibold">실제 수집 일정과 동일한지 확인했나요?</Dialog.Title><Dialog.Description>대시보드의 상태 판정 기준에만 적용됩니다.</Dialog.Description><p>변경 사유: {pending?.change_reason}</p><div className="flex gap-2"><Button disabled={busy} onClick={() => void save()}>{busy ? '저장 중…' : '확인하고 저장'}</Button><Button variant="outline" disabled={busy} onClick={() => setPending(null)}>취소</Button></div></Dialog.Content></Dialog.Portal></Dialog.Root>
  </section>
}
