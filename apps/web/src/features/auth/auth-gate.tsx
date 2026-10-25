import { useEffect, useState, type ReactNode, type FormEvent } from 'react'
import { Button } from '../../components/ui/button'
import { apiClient, setCsrfToken } from '../../lib/api'

export interface User { user_id: string; username: string; roles: string[] }
export function safeReturnTo(value: string | null) {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\r\n]/.test(value)) return '/'
  try {
    const url = new URL(value, window.location.origin)
    return url.origin === window.location.origin && url.pathname !== '/login' ? value : '/'
  } catch { return '/' }
}

export function AuthGate({ children, onExpired }: { children: (user: User, logout: () => Promise<void>) => ReactNode; onExpired: () => void }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [unavailable, setUnavailable] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    function expired() {
      setUser(null); setCsrfToken(null); onExpired()
      if (window.location.pathname !== '/login') {
        const target = window.location.pathname + window.location.search
        window.history.replaceState(null, '', '/login?returnTo=' + encodeURIComponent(target))
      }
    }
    window.addEventListener('monitoring-session-expired', expired)
    async function restore() {
      try {
        const me = await apiClient.get<User>('/api/v1/auth/me')
        const csrf = await apiClient.get<{ csrf_token: string }>('/api/v1/auth/csrf')
        if (active) {
          if (window.location.pathname === '/login') window.history.replaceState(null, '', safeReturnTo(new URLSearchParams(window.location.search).get('returnTo')))
          setCsrfToken(csrf.data.csrf_token); setUser(me.data)
        }
      } catch (err) {
        if (!active) return
        const code = (err as { response?: { status?: number } }).response?.status
        if (code === 401) expired()
        else { setError('세션을 확인할 수 없습니다. 잠시 후 다시 시도하세요.'); setUnavailable(true) }
      } finally { if (active) setLoading(false) }
    }
    void restore()
    return () => { active = false; window.removeEventListener('monitoring-session-expired', expired) }
  }, [onExpired])

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setBusy(true)
    const form = new FormData(event.currentTarget)
    try {
      const result = await apiClient.post('/api/v1/auth/login', { username: form.get('username'), password: form.get('password') })
      setCsrfToken(result.data.csrf_token); setUser(result.data.user)
      window.history.replaceState(null, '', safeReturnTo(new URLSearchParams(window.location.search).get('returnTo')))
    } catch { setError('로그인할 수 없습니다. 입력 값과 서버 상태를 확인하세요.') }
    finally { setBusy(false) }
  }
  async function logout() {
    try { await apiClient.post('/api/v1/auth/logout'); setUser(null); setCsrfToken(null); onExpired() }
    catch { setError('로그아웃하지 못했습니다. 다시 시도하세요.') }
  }
  if (loading) return <main className="p-8" role="status">로그인 상태 확인 중…</main>
  if (user) return <>{error && <p role="alert" className="p-3 text-destructive">{error}</p>}{children(user, logout)}</>
  return <main className="grid min-h-svh place-items-center bg-muted/30 p-6">
    <section className="w-full max-w-sm space-y-5 rounded-xl border bg-card p-8 shadow-sm">
      <div><p className="text-sm text-muted-foreground">데이터 수집 모니터링</p><h1 className="mt-2 text-2xl font-semibold">로그인</h1></div>
      {error && <p role="alert" id="login-error" className="text-sm text-destructive">{error}</p>}
      {unavailable ? <Button onClick={() => window.location.reload()}>다시 시도</Button> : <form onSubmit={login} className="space-y-4">
        <label className="block text-sm">아이디<input autoFocus name="username" autoComplete="username" required maxLength={100} className="mt-1 w-full rounded-md border bg-background p-2" /></label>
        <label className="block text-sm">비밀번호<input name="password" type="password" autoComplete="current-password" required maxLength={1024} aria-describedby={error ? 'login-error' : undefined} className="mt-1 w-full rounded-md border bg-background p-2" /></label>
        <Button className="w-full" disabled={busy}>{busy ? '확인 중…' : '로그인'}</Button>
      </form>}
    </section>
  </main>
}
