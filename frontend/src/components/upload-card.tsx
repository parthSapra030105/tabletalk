import { FileSpreadsheet, UploadCloud } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { api, type DatasetSummary } from '@/lib/api'
import { formatBytes } from '@/lib/format'
import { cn } from '@/lib/utils'

const MAX_BYTES = 250 * 1024 * 1024

export function UploadCard({ onUploaded }: { onUploaded: (d: DatasetSummary) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [dragging, setDragging] = useState(false)
  const [sent, setSent] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  function choose(f: File | undefined) {
    if (!f) return
    setError(null)
    // Quick checks here save a round trip; the server checks again properly.
    if (!f.name.toLowerCase().endsWith('.xlsx')) return setError('Choose an .xlsx workbook.')
    if (f.size > MAX_BYTES) return setError(`That file is ${formatBytes(f.size)}; the limit is 250 MB.`)
    setFile(f)
    setName(f.name.replace(/\.xlsx$/i, ''))
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    choose(e.dataTransfer.files[0])
  }

  async function upload() {
    if (!file) return
    setSent(0)
    setError(null)
    try {
      const dataset = await api.upload(file, name.trim() || undefined, setSent)
      toast.success(`Uploaded ${file.name}. Loading it now.`)
      onUploaded(dataset)
      setFile(null)
      setName('')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSent(null)
    }
  }

  return (
    <Card>
      <CardContent className="space-y-4">
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
            'flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-8 text-center transition-colors',
            dragging ? 'border-primary bg-primary/5' : 'hover:bg-muted/50',
          )}
        >
          {file ? (
            <>
              <FileSpreadsheet className="size-8 text-primary" />
              <div className="font-medium">{file.name}</div>
              <div className="text-sm text-muted-foreground">{formatBytes(file.size)} · click to choose another</div>
            </>
          ) : (
            <>
              <UploadCloud className="size-8 text-muted-foreground" />
              <div className="font-medium">Drop an Excel workbook here</div>
              <div className="text-sm text-muted-foreground">or click to browse · .xlsx up to 250 MB</div>
            </>
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
        </div>

        {file && (
          <div className="flex flex-col gap-3 sm:flex-row">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Dataset name" disabled={sent !== null} />
            <Button onClick={upload} disabled={sent !== null} className="sm:w-36">
              {sent === null ? 'Upload' : `Sending ${Math.round(sent * 100)}%`}
            </Button>
          </div>
        )}
        {sent !== null && <Progress value={sent * 100} />}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}
