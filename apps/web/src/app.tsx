import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'

import { MonitoringPage } from './features/monitoring/monitoring-page'

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

  return (
    <QueryClientProvider client={queryClient}>
      <MonitoringPage />
    </QueryClientProvider>
  )
}
