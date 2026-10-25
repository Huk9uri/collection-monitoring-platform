import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'

import { MonitoringPage } from './features/monitoring/monitoring-page'
import { AuthGate, type User } from './features/auth/auth-gate'
import { SchedulePage } from './features/monitoring-settings/schedule-page'
import { Button } from './components/ui/button'

export function App() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
          },
        },
      }),
  )
  const clearSession = useCallback(() => { queryClient.clear() }, [queryClient])

  return (
    <QueryClientProvider client={queryClient}>
      <AuthGate onExpired={clearSession}>{(user, logout) => <AuthenticatedApp user={user} logout={logout} />}</AuthGate>
    </QueryClientProvider>
  )
}

function AuthenticatedApp({ user, logout }: { user: User; logout: () => Promise<void> }) {
  const queryClient = useQueryClient()
  const [settings, showSettings] = useState(window.location.pathname === '/settings/schedules')
  return <>
        <nav aria-label="계정 및 설정" className="flex flex-wrap items-center justify-end gap-2 border-b bg-background p-3">
          <span className="mr-auto text-sm text-muted-foreground">{user.username}</span>
          <Button variant="ghost" onClick={() => { showSettings(false); window.history.replaceState(null, '', '/') }}>모니터링</Button>
          <Button variant="ghost" onClick={() => { showSettings(true); window.history.replaceState(null, '', '/settings/schedules') }}>모니터링 기준 일정</Button>
          <Button variant="outline" onClick={() => void logout()}>로그아웃</Button>
        </nav>
        {settings ? <SchedulePage admin={user.roles.includes('admin')} onPolicySaved={() => queryClient.removeQueries({ queryKey: ['monitoring'] })} /> : <MonitoringPage />}
      </>
}
