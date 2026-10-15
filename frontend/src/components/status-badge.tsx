import { CheckCircle2, Loader2, XCircle } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { DatasetStatus } from '@/lib/api'

const LABEL: Record<DatasetStatus, string> = {
  queued: 'Queued',
  loading: 'Loading rows',
  describing: 'Describing columns',
  ready: 'Ready',
  failed: 'Failed',
}

export function StatusBadge({ status }: { status: DatasetStatus }) {
  if (status === 'ready') {
    return (
      <Badge variant="outline" className="gap-1 border-emerald-500/30 text-emerald-700 dark:text-emerald-400">
        <CheckCircle2 className="size-3" /> {LABEL[status]}
      </Badge>
    )
  }
  if (status === 'failed') {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="size-3" /> {LABEL[status]}
      </Badge>
    )
  }
  return (
    <Badge variant="secondary" className="gap-1">
      <Loader2 className="size-3 animate-spin" /> {LABEL[status]}
    </Badge>
  )
}

export const inProgress = (s: DatasetStatus) => s === 'queued' || s === 'loading' || s === 'describing'
