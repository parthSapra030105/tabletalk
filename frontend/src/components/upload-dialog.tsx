import { FileSpreadsheet, UploadCloud, X } from 'lucide-react'
import { useEffect, useRef, useState, type DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { useAppData } from '@/context/app-data'
import { api } from '@/lib/api'
import { formatBytes } from '@/lib/format'
import { cn } from '@/lib/utils'

const MAX_BYTES = 250 * 1024 * 1024

function problemWith(f: File) {
  if (!f.name.toLowerCase().endsWith('.xlsx')) return 'Choose an .xlsx workbook. Save .xls or .csv files as .xlsx first.'
  if (f.size > MAX_BYTES) return `That file is ${formatBytes(f.size)}; the limit is 250 MB.`
  return null
}

export function UploadDialog() {
  const { upload, closeUpload, addDataset } = useAppData()
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [dragging, setDragging] = useState(false)
  const [sent, setSent] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  function choose(f: File | null | undefined) {
    setError(null)
    if (!f) return
    const problem = problemWith(f)
    if (problem) {
      setFile(null)
      return setError(problem)
    }
    setFile(f)
    setName(f.name.replace(/\.xlsx$/i, ''))
  }

  // A file dropped elsewhere on the page arrives with the open request.
  useEffect(() => {
    if (upload.open) choose(upload.file)
    else {
      setFile(null)
      setName('')
      setError(null)
    }
  }, [upload.open, upload.file])

  async function submit() {
    if (!file) return
    setSent(0)
    setError(null)
    try {
      const dataset = await api.upload(file, name.trim() || undefined, setSent)
      addDataset(dataset)
      toast.success(`Uploading ${dataset.name}`, { description: 'Reading sheets and loading rows. You can keep working.' })
      closeUpload()
      navigate('/')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSent(null)
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    e.stopPropagation() // handled here, not by the window-wide drop target
    setDragging(false)
    choose(e.dataTransfer.files[0])
  }

  return (
    <Dialog open={upload.open} onOpenChange={(open) => !open && sent === null && closeUpload()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload a workbook</DialogTitle>
          <DialogDescription>
            Every sheet is loaded into its own table. Messy headers, text dates and stray totals are cleaned up, and anything
            skipped is reported.
          </DialogDescription>
        </DialogHeader>

        {file ? (
          <div className="flex items-center gap-3 rounded-lg border bg-muted/40 p-3">
            <span className="flex size-9 items-center justify-center rounded-md bg-primary-soft text-primary">
              <FileSpreadsheet className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{file.name}</p>
              <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
            </div>
            {sent === null && (
              <Button variant="ghost" size="icon-sm" onClick={() => setFile(null)} aria-label="Remove file">
                <X />
              </Button>
            )}
          </div>
        ) : (
          <div
            role="button"
            tabIndex={0}
            onClick={() => input.current?.click()}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
              'flex flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center transition-colors',
              dragging ? 'border-primary bg-primary-soft' : 'hover:border-faint hover:bg-muted/40',
            )}
          >
            <UploadCloud className={cn('size-7', dragging ? 'text-primary' : 'text-faint')} />
            <p className="text-sm font-medium">Drop an .xlsx file, or click to browse</p>
            <p className="text-xs text-muted-foreground">Up to 250 MB · multiple sheets welcome</p>
          </div>
        )}
        <input
          ref={input}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="hidden"
          onChange={(e) => {
            choose(e.target.files?.[0])
            e.target.value = ''
          }}
        />

        {file && (
          <div className="space-y-1.5">
            <label htmlFor="dataset-name" className="eyebrow">
              Name
            </label>
            <Input id="dataset-name" value={name} onChange={(e) => setName(e.target.value)} disabled={sent !== null} />
          </div>
        )}

        {sent !== null && (
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Sending file</span>
              <span className="tabular-nums">{Math.round(sent * 100)}%</span>
            </div>
            <Progress value={sent * 100} />
          </div>
        )}
        {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-400">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={closeUpload} disabled={sent !== null}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!file || sent !== null}>
            {sent === null ? 'Upload' : 'Uploading…'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
