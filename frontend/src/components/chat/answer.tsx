import { BookOpen, ChevronRight, Database, Info, ShieldCheck, Sparkles, Table2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { ChartBlockView } from '@/components/chat/chart-block'
import { SqlBlockView } from '@/components/chat/sql-block'
import { TableBlockView } from '@/components/chat/table-block'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { Block, Message } from '@/lib/api'
import { formatCount } from '@/lib/format'
import { cn } from '@/lib/utils'

const ROUTES: Record<string, { label: string; icon: typeof Database; tone?: string }> = {
  data: { label: 'Answered with a query', icon: Database },
  write: { label: 'Refused · nothing ran', icon: ShieldCheck, tone: 'text-emerald-700 dark:text-emerald-400' },
  about_file: { label: 'From the catalog · no query', icon: BookOpen },
  define: { label: 'Saved to glossary', icon: BookOpen },
  vague: { label: 'Needs a narrower question', icon: Sparkles },
  off_topic: { label: 'Outside this data', icon: Info },
}

function Metrics({ blocks }: { blocks: Extract<Block, { type: 'metric' }>[] }) {
  return (
    <div className={cn('grid gap-3', blocks.length === 1 ? 'grid-cols-1 sm:w-64' : blocks.length === 2 ? 'grid-cols-2' : 'grid-cols-2 sm:grid-cols-3')}>
      {blocks.map((m, i) => (
        <div key={i} className="rounded-xl border bg-card px-4 py-3">
          <p className="eyebrow truncate">{m.label}</p>
          <p className="mt-1 text-xl font-semibold tracking-tight tabular-nums">{m.display}</p>
        </div>
      ))}
    </div>
  )
}

function HiddenTable({ children, rows }: { children: ReactNode; rows: number }) {
  const [open, setOpen] = useState(false)
  return open ? (
    <>{children}</>
  ) : (
    <button onClick={() => setOpen(true)} className="flex items-center gap-2 rounded-xl border bg-card px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">
      <ChevronRight className="size-3.5" />
      <Table2 className="size-3.5" />
      Show the {formatCount(rows)} row{rows === 1 ? '' : 's'} behind this
    </button>
  )
}

export function AnswerBlocks({ blocks, onAsk }: { blocks: Block[]; onAsk: (q: string) => void }) {
  const metrics = blocks.filter((b): b is Extract<Block, { type: 'metric' }> => b.type === 'metric')
  const hasChart = blocks.some((b) => b.type === 'bar_chart' || b.type === 'line_chart')
  let metricsShown = false

  return (
    <div className="space-y-3">
      {blocks.map((b, i) => {
        switch (b.type) {
          case 'text':
            return (
              <p key={i} className="text-[15px] leading-relaxed">
                {b.content}
              </p>
            )
          case 'metric':
            if (metricsShown) return null
            metricsShown = true
            return <Metrics key={i} blocks={metrics} />
          case 'bar_chart':
          case 'line_chart':
            return <ChartBlockView key={i} block={b} />
          case 'table':
            return hasChart ? (
              <HiddenTable key={i} rows={b.rows.length}>
                <TableBlockView columns={b.columns} rows={b.rows} />
              </HiddenTable>
            ) : (
              <TableBlockView key={i} columns={b.columns} rows={b.rows} />
            )
          case 'notice':
            return (
              <div key={i} className="flex gap-2.5 rounded-lg bg-muted/60 px-3.5 py-2.5 text-[13px] text-muted-foreground">
                <Info className="mt-0.5 size-3.5 shrink-0" />
                <p>{b.content}</p>
              </div>
            )
          case 'sql':
            return <SqlBlockView key={i} query={b.query} />
          case 'suggestions':
            return b.options.length ? (
              <div key={i} className="flex flex-wrap gap-2 pt-1">
                {b.options.map((o) => (
                  <button
                    key={o}
                    onClick={() => onAsk(o)}
                    className="rounded-full border bg-card px-3 py-1.5 text-left text-[13px] text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary-soft hover:text-primary"
                  >
                    {o}
                  </button>
                ))}
              </div>
            ) : null
          default:
            // A block type this page doesn't know: show it plainly rather than break the page.
            return (
              <pre key={i} className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs text-muted-foreground">
                {JSON.stringify(b, null, 2)}
              </pre>
            )
        }
      })}
    </div>
  )
}

export function AnswerFooter({ message }: { message: Message }) {
  const route = ROUTES[message.route] ?? { label: 'Answer', icon: Info }
  const Icon = route.icon
  return (
    <div className="mt-3 flex items-center gap-3 text-[11px] text-faint">
      <span className={cn('inline-flex items-center gap-1', route.tone)}>
        <Icon className="size-3" /> {route.label}
      </span>
      {message.total_tokens > 0 && (
        <Tooltip>
          <TooltipTrigger className="tabular-nums hover:text-muted-foreground">
            {formatCount(message.total_tokens)} tokens · {message.seconds}s
          </TooltipTrigger>
          <TooltipContent className="text-xs">
            {message.usage.map((u, i) => (
              <div key={i} className="flex justify-between gap-6 tabular-nums">
                <span>{u.purpose}</span>
                <span>{formatCount(u.total_tokens)}</span>
              </div>
            ))}
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}
