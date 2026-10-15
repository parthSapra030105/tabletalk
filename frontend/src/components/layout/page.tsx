import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

const WIDTH = { '3xl': 'max-w-3xl', '4xl': 'max-w-4xl', '5xl': 'max-w-5xl', '6xl': 'max-w-6xl' } as const

export function Page({ children, width = '6xl', className }: { children: ReactNode; width?: keyof typeof WIDTH; className?: string }) {
  return (
    <div className="h-full overflow-y-auto scrollbar-slim">
      <div className={cn('mx-auto animate-fade-up px-4 py-8 sm:px-8 sm:py-10', WIDTH[width], className)}>{children}</div>
    </div>
  )
}

export function PageHeader({ title, subtitle, eyebrow, right }: { title: ReactNode; subtitle?: ReactNode; eyebrow?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  )
}

export function SectionHeader({ title, count, right, className }: { title: string; count?: number; right?: ReactNode; className?: string }) {
  return (
    <div className={cn('mb-3 flex items-baseline justify-between', className)}>
      <h2 className="eyebrow">
        {title}
        {typeof count === 'number' && <span className="ml-2 text-faint tabular-nums">{count}</span>}
      </h2>
      {right && <div className="text-xs text-muted-foreground">{right}</div>}
    </div>
  )
}

export function KpiCard({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-xl border bg-card p-5">
      <p className="eyebrow mb-1.5">{label}</p>
      <p className="text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

export function EmptyState({ icon, title, hint, action }: { icon?: ReactNode; title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed bg-card px-6 py-12 text-center">
      {icon && <div className="mb-3 flex size-10 items-center justify-center rounded-lg border bg-background text-muted-foreground [&_svg]:size-5">{icon}</div>}
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="mt-1 max-w-sm text-xs text-muted-foreground">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
