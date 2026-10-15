import { LayoutGrid, MessageSquare, Plus, Table2, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { StatusDot } from '@/components/status-pill'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { useAppData } from '@/context/app-data'
import { api, type ThreadSummary } from '@/lib/api'
import { formatCompact } from '@/lib/format'
import { cn } from '@/lib/utils'

const item = 'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors'
const idle = 'text-sidebar-foreground hover:bg-sidebar-accent/70 hover:text-foreground'
const active = 'bg-primary-soft font-medium text-primary'

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="flex h-7 items-center justify-between px-2.5">
        <span className="eyebrow">{title}</span>
        {action}
      </div>
      {children}
    </div>
  )
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { datasetId, threadId } = useParams()
  const { datasets, openUpload, threadsVersion, bumpThreads } = useAppData()
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const navigate = useNavigate()
  const current = datasets?.find((d) => String(d.id) === datasetId)

  useEffect(() => {
    if (!datasetId) return setThreads([])
    api.threads(Number(datasetId)).then(setThreads).catch(() => setThreads([]))
  }, [datasetId, threadsVersion])

  async function newChat() {
    if (!current) return
    try {
      const t = await api.newThread(current.id)
      bumpThreads()
      navigate(`/datasets/${current.id}/chat/${t.id}`)
      onNavigate?.()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <div className="flex h-full flex-col bg-sidebar">
      <div className="flex h-14 shrink-0 items-center gap-2.5 px-4">
        <Link to="/" onClick={onNavigate} className="flex items-center gap-2.5">
          <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <Table2 className="size-4" />
          </span>
          <span className="text-[15px] font-semibold tracking-tight">Tabletalk</span>
        </Link>
      </div>

      <div className="px-3 pb-3">
        <Button className="w-full" onClick={() => openUpload()}>
          <Upload /> Upload workbook
        </Button>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4 scrollbar-slim">
        <NavLink to="/" end onClick={onNavigate} className={({ isActive }) => cn(item, isActive ? active : idle)}>
          <LayoutGrid className="size-4" /> All datasets
        </NavLink>

        <Section title="Datasets">
          {datasets === null && <p className="px-2.5 text-xs text-faint">Loading…</p>}
          {datasets?.length === 0 && <p className="px-2.5 text-xs text-faint">No datasets yet</p>}
          {datasets?.map((d) => (
            <NavLink
              key={d.id}
              to={d.status === 'ready' ? `/datasets/${d.id}/chat` : `/datasets/${d.id}`}
              onClick={onNavigate}
              className={cn(item, String(d.id) === datasetId ? active : idle)}
            >
              <StatusDot status={d.status} />
              <span className="min-w-0 flex-1 truncate">{d.name}</span>
              {d.status === 'ready' && <span className="text-[11px] text-faint tabular-nums">{formatCompact(d.rows)}</span>}
            </NavLink>
          ))}
        </Section>

        {current?.status === 'ready' && (
          <Section
            title="Chats"
            action={
              <button onClick={newChat} className="rounded-md p-1 text-muted-foreground hover:bg-sidebar-accent hover:text-foreground" aria-label="New chat">
                <Plus className="size-3.5" />
              </button>
            }
          >
            {threads.length === 0 && <p className="px-2.5 text-xs text-faint">No chats yet</p>}
            {threads.map((t) => (
              <NavLink
                key={t.id}
                to={`/datasets/${current.id}/chat/${t.id}`}
                onClick={onNavigate}
                className={cn(item, 'py-1.5', t.id === threadId ? active : idle)}
              >
                <MessageSquare className="size-3.5 shrink-0 opacity-60" />
                <span className="min-w-0 flex-1 truncate">{t.title || 'New chat'}</span>
              </NavLink>
            ))}
          </Section>
        )}
      </nav>

      <div className="flex items-center justify-between border-t border-sidebar-border px-4 py-3">
        <span className="text-[11px] leading-tight text-faint">
          Read-only · every number
          <br />
          comes from a query
        </span>
        <ThemeToggle />
      </div>
    </div>
  )
}
