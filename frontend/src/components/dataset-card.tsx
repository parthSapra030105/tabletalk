import { Database, MessageSquare, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { StatusBadge, inProgress } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import { api, type DatasetSummary } from '@/lib/api'
import { formatCount } from '@/lib/format'

function timeAgo(iso: string) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

function LoadingState({ d }: { d: DatasetSummary }) {
  if (d.status === 'describing') {
    return <p className="text-sm text-muted-foreground">Rows are in. Writing a description for each column…</p>
  }
  const { sheet, rows, total } = d.progress
  if (!sheet || !total) return <p className="text-sm text-muted-foreground">Reading the workbook…</p>
  const pct = Math.min(100, ((rows ?? 0) / total) * 100)
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm text-muted-foreground">
        <span>Loading {sheet}</span>
        <span className="tabular-nums">
          {formatCount(rows ?? 0)} / ~{formatCount(total)} rows
        </span>
      </div>
      <Progress value={pct} />
    </div>
  )
}

export function DatasetCard({ dataset: d, onDeleted }: { dataset: DatasetSummary; onDeleted: () => void }) {
  const [deleting, setDeleting] = useState(false)

  async function remove() {
    setDeleting(true)
    try {
      await api.deleteDataset(d.id)
      toast.success(`Deleted ${d.name}`)
      onDeleted()
    } catch (e) {
      toast.error((e as Error).message)
      setDeleting(false)
    }
  }

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="leading-snug">{d.name}</CardTitle>
          <StatusBadge status={d.status} />
        </div>
        <CardDescription className="flex flex-wrap items-center gap-2">
          {d.is_sample && <Badge variant="outline">Sample</Badge>}
          <span>Added {timeAgo(d.created_at)}</span>
        </CardDescription>
      </CardHeader>

      <CardContent className="flex-1">
        {inProgress(d.status) && <LoadingState d={d} />}
        {d.status === 'failed' && <p className="text-sm text-destructive">{d.error}</p>}
        {d.status === 'ready' && (
          <div className="flex gap-6 text-sm">
            <div>
              <div className="text-2xl font-semibold tabular-nums">{d.tables}</div>
              <div className="text-muted-foreground">sheets</div>
            </div>
            <div>
              <div className="text-2xl font-semibold tabular-nums">{formatCount(d.rows)}</div>
              <div className="text-muted-foreground">rows</div>
            </div>
          </div>
        )}
      </CardContent>

      <CardFooter className="gap-2">
        {d.status === 'ready' && (
          <>
            <Button asChild size="sm">
              <Link to={`/datasets/${d.id}/chat`}>
                <MessageSquare /> Ask questions
              </Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link to={`/datasets/${d.id}`}>
                <Database /> Details
              </Link>
            </Button>
          </>
        )}
        {!inProgress(d.status) && (
          <Dialog>
            <DialogTrigger asChild>
              <Button size="icon-sm" variant="ghost" className="ml-auto text-muted-foreground" aria-label="Delete dataset">
                <Trash2 />
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete “{d.name}”?</DialogTitle>
                <DialogDescription>
                  This removes its tables, its catalog and every conversation about it. The original file is not affected.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline">Cancel</Button>
                </DialogClose>
                <Button variant="destructive" onClick={remove} disabled={deleting}>
                  {deleting ? 'Deleting…' : 'Delete'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </CardFooter>
    </Card>
  )
}
