import type { ReactNode } from 'react'

import { Header } from './header'
import { Sidebar } from './sidebar'

interface AppLayoutProps {
  children: ReactNode
  header?: ReactNode
}

export function AppLayout({ children, header }: AppLayoutProps) {
  return (
    <div className="min-h-svh bg-muted/30 md:grid md:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="hidden border-r border-sidebar-border md:block">
        <Sidebar className="sticky top-0 h-svh" />
      </aside>
      <div className="min-w-0">
        <Header>{header}</Header>
        <main id="monitoring" className="mx-auto w-full max-w-screen-2xl p-4 sm:p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
