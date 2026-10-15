import { ArrowRight, Info, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { StatusPill } from '@/components/status-pill'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { isLoading, useAppData } from '@/context/app-data'
import { api, type DatasetSummary } from '@/lib/api'
import { formatBytes, formatCompact, formatCount } from '@/lib/format'

export function timeAgo(iso: string) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

function Progressing({ d }: { d: DatasetSummary }) {
  if (d.status === 'describing') return <span className="text-xs text-muted-foreground">Describing columns…</span>
  const { sheet, rows, total } = d.progress
  if (!sheet || !total) return <span className="text-xs text-muted-foreground">Reading workbook…</span>
  const pct = Math.min(100, ((rows ?? 0) / total) * 100)
  return (
    <div className="w-40 space-y-1">
      <div className="flex justify-between text-[11px] text-muted-foreground">
        <span className="truncate">{sheet}</span>
        <span className="tabular-nums">
          {formatCompact(rows ?? 0)} / {formatCompact(total)}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-amber-500 transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

const th = 'px-4 py-2.5 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground'

export function DatasetsTable({ datasets }: { datasets: DatasetSummary[] }) {
  const navigate = useNavigate()
  const { refreshDatasets } = useAppData()
  const [toDelete, setToDelete] = useState<DatasetSummary | null>(null)
  const [deleting, setDeleting] = useState(false)

  async function remove() {
    if (!toDelete) return
    setDeleting(true)
    try {
      await api.deleteDataset(toDelete.id)
      toast.success(`Deleted ${toDelete.name}`)
      await refreshDatasets()
      setToDelete(null)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <>
      <div className="overflow-hidden rounded-xl border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/40">
            <tr>
              <th className={th}>Dataset</th>
              <th className={th}>Status</th>
              <th className={`${th} hidden text-right md:table-cell`}>Sheets</th>
              <th className={`${th} text-right`}>Rows</th>
              <th className={`${th} hidden text-right sm:table-cell`}>Added</th>
              <th className={th}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {datasets.map((d) => {
              const ready = d.status === 'ready'
              return (
                <tr
                  key={d.id}
                  onClick={() => ready && navigate(`/datasets/${d.id}/chat`)}
                  className={`group border-b border-border-subtle last:border-0 ${ready ? 'cursor-pointer hover:bg-muted/40' : ''}`}
                >
                  <td className="max-w-0 px-4 py-3.5">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">{d.name}</span>
                      {d.is_sample && (
                        <span className="shrink-0 rounded px-1.5 py-px text-[10px] font-medium text-primary ring-1 ring-primary/25 ring-inset">
                          Sample
                        </span>
                      )}
                    </div>
                    <p className={`mt-0.5 truncate text-xs ${d.status === 'failed' ? 'text-rose-600 dark:text-rose-400' : 'text-muted-foreground'}`}>
                      {d.status === 'failed' ? d.error : `${formatBytes(d.file_size)}${d.threads ? ` · ${d.threads} chat${d.threads > 1 ? 's' : ''}` : ''}`}
                    </p>
                  </td>
                  <td className="px-4 py-3.5">{isLoading(d.status) ? <Progressing d={d} /> : <StatusPill status={d.status} />}</td>
                  <td className="hidden px-4 py-3.5 text-right tabular-nums md:table-cell">{ready ? d.tables : '—'}</td>
                  <td className="px-4 py-3.5 text-right tabular-nums">{ready ? formatCount(d.rows) : '—'}</td>
                  <td className="hidden px-4 py-3.5 text-right text-muted-foreground sm:table-cell">{timeAgo(d.created_at)}</td>
                  <td className="px-3 py-3.5" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-1">
                      {ready && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button asChild variant="ghost" size="icon-sm" className="text-muted-foreground">
                              <Link to={`/datasets/${d.id}`} aria-label="Dataset details">
                                <Info />
                              </Link>
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Load report and columns</TooltipContent>
                        </Tooltip>
                      )}
                      {!isLoading(d.status) && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-rose-600" onClick={() => setToDelete(d)} aria-label="Delete dataset">
                              <Trash2 />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Delete</TooltipContent>
                        </Tooltip>
                      )}
                      {ready && (
                        <Button asChild size="sm" variant="outline" className="ml-1 hidden sm:inline-flex">
                          <Link to={`/datasets/${d.id}/chat`}>
                            Ask <ArrowRight />
                          </Link>
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <Dialog open={toDelete !== null} onOpenChange={(open) => !open && !deleting && setToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete “{toDelete?.name}”?</DialogTitle>
            <DialogDescription>
              This removes its tables, its catalog and every conversation about it. Your original file isn't affected.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button variant="destructive" onClick={remove} disabled={deleting}>
              {deleting ? 'Deleting…' : 'Delete dataset'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
