import type { DatasetStatus } from '@/lib/api'
import { cn } from '@/lib/utils'

// Ringed pills: tinted background, stronger text, a hairline ring of the same hue.
const TONE: Record<DatasetStatus, { label: string; className: string; dot: string; pulse?: boolean }> = {
  ready: {
    label: 'Ready',
    className: 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20',
    dot: 'bg-emerald-500',
  },
  queued: {
    label: 'Queued',
    className: 'bg-stone-100 text-stone-600 ring-stone-200 dark:bg-white/5 dark:text-stone-300 dark:ring-white/10',
    dot: 'bg-stone-400',
    pulse: true,
  },
  loading: {
    label: 'Loading',
    className: 'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20',
    dot: 'bg-amber-500',
    pulse: true,
  },
  describing: {
    label: 'Describing',
    className: 'bg-primary-soft text-primary ring-primary/20',
    dot: 'bg-primary',
    pulse: true,
  },
  failed: {
    label: 'Failed',
    className: 'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-500/10 dark:text-rose-400 dark:ring-rose-500/20',
    dot: 'bg-rose-500',
  },
}

export function StatusDot({ status, className }: { status: DatasetStatus; className?: string }) {
  const tone = TONE[status]
  return (
    <span className={cn('relative flex size-2 shrink-0', className)}>
      {tone.pulse && <span className={cn('absolute inline-flex size-full animate-ping rounded-full opacity-60', tone.dot)} />}
      <span className={cn('relative inline-flex size-2 rounded-full', tone.dot)} />
    </span>
  )
}

export function StatusPill({ status }: { status: DatasetStatus }) {
  const tone = TONE[status]
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset', tone.className)}>
      <StatusDot status={status} className="size-1.5 [&>span]:size-1.5" />
      {tone.label}
    </span>
  )
}
