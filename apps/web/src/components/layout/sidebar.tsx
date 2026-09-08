import { ActivityIcon, LayoutDashboardIcon } from 'lucide-react'
import type { ComponentProps } from 'react'

import { cn } from '../../lib/utils'

export function Sidebar({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'flex h-full flex-col bg-sidebar text-sidebar-foreground',
        className,
      )}
      {...props}
    >
      <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-5">
        <span className="flex size-9 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
          <ActivityIcon className="size-5" aria-hidden="true" />
        </span>
        <span className="text-sm font-semibold">데이터 수집 모니터링</span>
      </div>

      <nav aria-label="주요 메뉴" className="flex-1 p-3">
        <a
          href="#monitoring"
          aria-current="page"
          className="flex items-center gap-3 rounded-md bg-sidebar-accent px-3 py-2 text-sm font-medium text-sidebar-accent-foreground outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
        >
          <LayoutDashboardIcon className="size-4" aria-hidden="true" />
          모니터링
        </a>
      </nav>
    </div>
  )
}
