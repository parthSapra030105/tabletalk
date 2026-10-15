import { AlertCircle, AlertTriangle, ArrowRight, BookOpen, ChevronDown, Link2, Loader2, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { EmptyState, KpiCard, Page, PageHeader, SectionHeader } from '@/components/layout/page'
import { StatusPill } from '@/components/status-pill'
import { TypeChip } from '@/components/type-chip'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { isLoading } from '@/context/app-data'
import { api, type CatalogTable, type DatasetDetail, type GlossaryEntry, type SheetReport } from '@/lib/api'
import { formatCompact, formatCount } from '@/lib/format'
import { cn } from '@/lib/utils'

const th = 'px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground'
const td = 'px-4 py-2.5 align-top'
const PREVIEW_COLUMNS = 12

function useDataset(id: number) {
  const [dataset, setDataset] = useState<DatasetDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setDataset(await api.dataset(id))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [id])

  useEffect(() => {
    setDataset(null)
    load()
  }, [load])

  useEffect(() => {
    if (!dataset || !isLoading(dataset.status)) return
    const timer = setInterval(load, 1500)
    return () => clearInterval(timer)
  }, [dataset, load])

  return { dataset, error }
}

function ShowMore({ open, total, onToggle }: { open: boolean; total: number; onToggle: () => void }) {
  if (total <= PREVIEW_COLUMNS) return null
  return (
    <button onClick={onToggle} className="flex w-full items-center justify-center gap-1 border-t border-border-subtle py-2 text-xs font-medium text-muted-foreground hover:bg-muted/40 hover:text-foreground">
      {open ? 'Show fewer' : `Show all ${total} columns`}
      <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} />
    </button>
  )
}

// --- Load report ----------------------------------------------------------------

function SheetCard({ sheet }: { sheet: SheetReport }) {
  const [open, setOpen] = useState(false)
  if (sheet.status === 'skipped') {
    return (
      <div className="flex items-center justify-between rounded-xl border bg-card px-5 py-4">
        <div>
          <p className="font-medium">{sheet.sheet}</p>
          <p className="text-xs text-muted-foreground">Not loaded: {sheet.reason}</p>
        </div>
        <span className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">Skipped</span>
      </div>
    )
  }
  const skipped = Object.entries(sheet.skipped_rows)
  const skippedTotal = skipped.reduce((n, [, s]) => n + s.count, 0)
  const columns = open ? sheet.columns : sheet.columns.slice(0, PREVIEW_COLUMNS)

  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
        <div className="min-w-0">
          <p className="font-medium">
            {sheet.sheet} <span className="font-normal text-muted-foreground">→</span>{' '}
            <code className="font-mono text-sm text-primary">{sheet.table}</code>
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Header found on row {sheet.header_row}
            {sheet.header_row && sheet.header_row > 1 ? ` (${sheet.header_row - 1} title or blank row${sheet.header_row > 2 ? 's' : ''} above it ignored)` : ''}
            {' · '}
            {sheet.columns.length} columns
          </p>
        </div>
        <div className="text-right">
          <p className="text-lg font-semibold tabular-nums">{formatCount(sheet.rows_loaded)}</p>
          <p className="text-xs text-muted-foreground">rows loaded</p>
        </div>
      </div>

      {skippedTotal > 0 && (
        <div className="mx-5 mb-4 space-y-1.5 rounded-lg bg-amber-50 px-4 py-3 text-sm ring-1 ring-amber-200 ring-inset dark:bg-amber-500/10 dark:ring-amber-500/20">
          <p className="font-medium text-amber-800 dark:text-amber-300">
            {formatCount(skippedTotal)} row{skippedTotal > 1 ? 's' : ''} skipped
          </p>
          {skipped.map(([reason, s]) => (
            <p key={reason} className="text-amber-800/80 dark:text-amber-300/80">
              <span className="tabular-nums">{formatCount(s.count)}</span> × {reason}
              <span className="text-xs"> (e.g. row{s.examples.length > 1 ? 's' : ''} {s.examples.join(', ')})</span>
            </p>
          ))}
        </div>
      )}

      <div className="overflow-x-auto border-t">
        <table className="w-full text-sm">
          <thead className="bg-muted/40">
            <tr>
              <th className={th}>Header in the file</th>
              <th className={th}>Column</th>
              <th className={th}>Type</th>
              <th className={`${th} text-right`}>Empty</th>
              <th className={th}>Notes</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((c) => (
              <tr key={c.name} className="border-t border-border-subtle">
                <td className={cn(td, 'max-w-56 truncate')}>{c.original ?? <span className="italic text-faint">blank header</span>}</td>
                <td className={td}>
                  <code className="font-mono text-[13px]">{c.name}</code>
                </td>
                <td className={td}>
                  <TypeChip type={c.type} />
                </td>
                <td className={cn(td, 'text-right tabular-nums text-muted-foreground')}>{c.nulls ? formatCompact(c.nulls) : '—'}</td>
                <td className={cn(td, 'text-xs text-muted-foreground')}>
                  {c.coercion_failures > 0 && (
                    <span className="mr-2 text-amber-700 dark:text-amber-400">
                      {formatCount(c.coercion_failures)} unreadable value{c.coercion_failures > 1 ? 's' : ''} left empty
                    </span>
                  )}
                  {c.note}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ShowMore open={open} total={sheet.columns.length} onToggle={() => setOpen(!open)} />
    </div>
  )
}

// --- Columns and meaning ----------------------------------------------------------

function TableMeaning({ table }: { table: CatalogTable }) {
  const [open, setOpen] = useState(false)
  const columns = open ? table.columns : table.columns.slice(0, PREVIEW_COLUMNS)
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div className="px-5 py-4">
        <p className="font-medium">
          <code className="font-mono text-primary">{table.name}</code>
          <span className="ml-2 text-sm font-normal text-muted-foreground tabular-nums">{formatCount(table.rows)} rows</span>
        </p>
        {table.description && <p className="mt-1 text-sm text-muted-foreground">{table.description}</p>}
      </div>
      {table.ambiguities.length > 0 && (
        <div className="mx-5 mb-4 space-y-2">
          {table.ambiguities.map((a) => (
            <div key={a.columns.join()} className="flex gap-2.5 rounded-lg bg-primary-soft px-3.5 py-2.5 text-sm">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-primary" />
              <p>
                <span className="font-medium">Easily confused: </span>
                {a.columns.map((c, i) => (
                  <span key={c}>
                    {i > 0 && ' / '}
                    <code className="font-mono text-[13px]">{c}</code>
                  </span>
                ))}
                <span className="text-muted-foreground"> · {a.note}</span>
              </p>
            </div>
          ))}
        </div>
      )}
      <table className="w-full border-t text-sm">
        <tbody>
          {columns.map((c) => (
            <tr key={c.name} className="border-t border-border-subtle first:border-0">
              <td className={cn(td, 'w-56')}>
                <code className="font-mono text-[13px]">{c.name}</code>
                {c.original && c.original !== c.name && <p className="truncate text-xs text-faint">{c.original}</p>}
              </td>
              <td className={cn(td, 'w-28')}>
                <TypeChip type={c.type} />
              </td>
              <td className={cn(td, 'text-muted-foreground')}>
                {c.description.startsWith('Unclear:') ? (
                  <span className="text-amber-700 dark:text-amber-400">{c.description}</span>
                ) : (
                  c.description || <span className="text-faint">No description</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ShowMore open={open} total={table.columns.length} onToggle={() => setOpen(!open)} />
    </div>
  )
}

// --- Glossary -------------------------------------------------------------------

function Glossary({ datasetId }: { datasetId: number }) {
  const [entries, setEntries] = useState<GlossaryEntry[] | null>(null)

  useEffect(() => {
    api.glossary(datasetId).then(setEntries).catch(() => setEntries([]))
  }, [datasetId])

  async function remove(term: string) {
    try {
      await api.deleteGlossaryEntry(datasetId, term)
      setEntries((e) => e?.filter((x) => x.term !== term) ?? null)
      toast.success(`“${term}” will be interpreted afresh again`)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  if (entries === null) return <Skeleton className="h-24 rounded-xl" />
  if (entries.length === 0)
    return (
      <EmptyState
        icon={<BookOpen />}
        title="No definitions yet"
        hint={
          <>
            Tell the assistant what a term means, e.g. <span className="text-foreground">“revenue means net amount excluding cancelled orders”</span>, and
            it will apply that to every later question on this dataset.
          </>
        }
      />
    )
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      {entries.map((e) => (
        <div key={e.term} className="flex items-start gap-4 border-b border-border-subtle px-5 py-4 last:border-0">
          <div className="min-w-0 flex-1">
            <p className="font-medium">“{e.term}”</p>
            <p className="mt-0.5 text-sm text-muted-foreground">{e.meaning}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {e.columns.map((c) => (
                <code key={c} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                  {c}
                </code>
              ))}
            </div>
          </div>
          <Button variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-rose-600" onClick={() => remove(e.term)} aria-label={`Remove ${e.term}`}>
            <Trash2 />
          </Button>
        </div>
      ))}
    </div>
  )
}

// --- Page -----------------------------------------------------------------------

export default function DatasetPage() {
  const id = Number(useParams().datasetId)
  const { dataset: d, error } = useDataset(id)

  if (error)
    return (
      <Page>
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>Couldn't open this dataset</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </Page>
    )
  if (!d)
    return (
      <Page>
        <Skeleton className="mb-8 h-14 w-80" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      </Page>
    )

  const loaded = d.sheets.filter((s) => s.status === 'loaded')
  const skippedRows = loaded.reduce((n, s) => n + Object.values(s.skipped_rows).reduce((m, r) => m + r.count, 0), 0)
  const columnCount = loaded.reduce((n, s) => n + s.columns.length, 0)
  const loadTime = d.timings.load_seconds

  return (
    <Page>
      <PageHeader
        eyebrow="Dataset"
        title={d.name}
        subtitle={
          <span className="inline-flex flex-wrap items-center gap-2">
            <StatusPill status={d.status} />
            {d.status === 'ready' && (
              <span>
                {loaded.length} sheets · {formatCount(d.rows)} rows{loadTime ? ` · loaded in ${loadTime}s` : ''}
              </span>
            )}
          </span>
        }
        right={
          d.status === 'ready' && (
            <Button asChild>
              <Link to={`/datasets/${d.id}/chat`}>
                Ask questions <ArrowRight />
              </Link>
            </Button>
          )
        }
      />

      {isLoading(d.status) && (
        <div className="flex items-center gap-3 rounded-xl border bg-card px-5 py-4 text-sm">
          <Loader2 className="size-4 animate-spin text-primary" />
          {d.status === 'describing'
            ? 'Rows are loaded. Writing a one-line description for every column…'
            : d.progress.sheet
              ? `Loading ${d.progress.sheet}: ${formatCount(d.progress.rows ?? 0)} of ~${formatCount(d.progress.total ?? 0)} rows`
              : 'Reading the workbook…'}
        </div>
      )}
      {d.status === 'failed' && (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>This workbook couldn't be loaded</AlertTitle>
          <AlertDescription>{d.error}</AlertDescription>
        </Alert>
      )}

      {d.status === 'ready' && (
        <>
          <div className="mb-10 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="Rows loaded" value={formatCompact(d.rows)} hint={`${formatCount(d.rows)} exactly`} />
            <KpiCard label="Sheets" value={loaded.length} hint={`${d.sheets.length - loaded.length || 'none'} skipped`} />
            <KpiCard label="Columns" value={columnCount} hint="typed and described" />
            <KpiCard label="Rows skipped" value={formatCount(skippedRows)} hint="blank, totals, duplicates" />
          </div>

          <Tabs defaultValue="report">
            <TabsList className="mb-5">
              <TabsTrigger value="report">Load report</TabsTrigger>
              <TabsTrigger value="columns">Columns</TabsTrigger>
              <TabsTrigger value="joins">Joins</TabsTrigger>
              <TabsTrigger value="glossary">Glossary</TabsTrigger>
            </TabsList>

            <TabsContent value="report" className="space-y-4">
              <SectionHeader title="Sheets found" count={d.sheets.length} right={d.timings.describe_seconds ? `Descriptions written in ${d.timings.describe_seconds}s` : undefined} />
              {d.sheets.map((s) => (
                <SheetCard key={s.sheet} sheet={s} />
              ))}
            </TabsContent>

            <TabsContent value="columns" className="space-y-4">
              <SectionHeader title="What each column means" right="Written once at upload, reused for every question" />
              {d.catalog.tables.map((t) => (
                <TableMeaning key={t.name} table={t} />
              ))}
            </TabsContent>

            <TabsContent value="joins">
              <SectionHeader title="Detected relationships" count={d.catalog.joins.length} right="Found by matching values, not names" />
              {d.catalog.joins.length === 0 ? (
                <EmptyState icon={<Link2 />} title="No relationships found" hint="Each sheet will be queried on its own." />
              ) : (
                <div className="overflow-hidden rounded-xl border bg-card">
                  {d.catalog.joins.map((j) => (
                    <div key={`${j.from_table}.${j.from_column}`} className="flex flex-wrap items-center gap-3 border-b border-border-subtle px-5 py-3.5 last:border-0">
                      <code className="font-mono text-sm">
                        {j.from_table}.<span className="text-primary">{j.from_column}</span>
                      </code>
                      <ArrowRight className="size-4 text-faint" />
                      <code className="font-mono text-sm">
                        {j.to_table}.<span className="text-primary">{j.to_column}</span>
                      </code>
                      <span className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
                        {j.one_to_one && <span className="rounded bg-muted px-1.5 py-0.5">one-to-one</span>}
                        <span className="tabular-nums">{Math.round(j.overlap * 100)}% of values match</span>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="glossary">
              <SectionHeader title="Your definitions" right="Applied to every question on this dataset" />
              <Glossary datasetId={d.id} />
            </TabsContent>
          </Tabs>
        </>
      )}
    </Page>
  )
}
