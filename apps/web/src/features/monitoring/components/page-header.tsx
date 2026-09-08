import { RefreshCwIcon } from 'lucide-react'

import { Button } from '../../../components/ui/button'

interface PageHeaderProps {
  onRefresh: () => void
  isRefreshing: boolean
}

export function PageHeader({ onRefresh, isRefreshing }: PageHeaderProps) {
  return (
    <div className="flex min-w-0 flex-1 items-center justify-between gap-3">
      <h1 className="truncate text-base font-semibold sm:text-lg">
        데이터 수집 모니터링
      </h1>
      <Button
        type="button"
        variant="outline"
        onClick={onRefresh}
        disabled={isRefreshing}
        aria-label="새로고침"
      >
        <RefreshCwIcon
          className={isRefreshing ? 'animate-spin' : undefined}
          aria-hidden="true"
        />
        <span className="hidden sm:inline">
          {isRefreshing ? '새로고침 중' : '새로고침'}
        </span>
      </Button>
    </div>
  )
}
