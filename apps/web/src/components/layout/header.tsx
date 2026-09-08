import { MenuIcon } from 'lucide-react'
import type { ComponentProps } from 'react'

import { cn } from '../../lib/utils'
import { Button } from '../ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '../ui/sheet'
import { Sidebar } from './sidebar'

export function Header({
  className,
  children,
  ...props
}: ComponentProps<'header'>) {
  return (
    <header
      className={cn(
        'sticky top-0 z-40 flex h-16 items-center gap-3 border-b bg-background/95 px-4 backdrop-blur sm:px-6',
        className,
      )}
      {...props}
    >
      <Sheet>
        <SheetTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="메뉴 열기"
            className="md:hidden"
          >
            <MenuIcon aria-hidden="true" />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>모바일 메뉴</SheetTitle>
            <SheetDescription>데이터 수집 모니터링 탐색</SheetDescription>
          </SheetHeader>
          <Sidebar />
        </SheetContent>
      </Sheet>
      {children}
    </header>
  )
}
