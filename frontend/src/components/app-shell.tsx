import { Table2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { ThemeToggle } from '@/components/theme-toggle'

export function AppShell({ children, crumbs }: { children: ReactNode; crumbs?: ReactNode }) {
  return (
    <div className="flex h-dvh flex-col">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Table2 className="size-4" />
          </span>
          Tabletalk
        </Link>
        {crumbs && <div className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">{crumbs}</div>}
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </header>
      <main className="min-h-0 flex-1">{children}</main>
    </div>
  )
}
