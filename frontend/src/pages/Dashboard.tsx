import { AlertCircle, FileSpreadsheet, Upload } from 'lucide-react'

import { DatasetsTable } from '@/components/datasets-table'
import { EmptyState, KpiCard, Page, PageHeader, SectionHeader } from '@/components/layout/page'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { isLoading, useAppData } from '@/context/app-data'
import { formatCompact } from '@/lib/format'

export default function DashboardPage() {
  const { datasets, datasetsError, openUpload } = useAppData()
  const ready = datasets?.filter((d) => d.status === 'ready') ?? []
  const loading = datasets?.filter((d) => isLoading(d.status)).length ?? 0

  return (
    <Page>
      <PageHeader
        eyebrow="Workspace"
        title="Datasets"
        subtitle="Upload a workbook and ask about it in plain language. Answers are built from read-only queries, and every number links back to the SQL that produced it."
        right={
          <Button onClick={() => openUpload()}>
            <Upload /> Upload workbook
          </Button>
        }
      />

      {datasetsError && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle />
          <AlertTitle>Couldn't reach the server</AlertTitle>
          <AlertDescription>{datasetsError}</AlertDescription>
        </Alert>
      )}

      <div className="mb-10 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Datasets" value={datasets ? ready.length : '—'} hint={loading ? `${loading} loading now` : 'ready to query'} />
        <KpiCard label="Rows loaded" value={datasets ? formatCompact(ready.reduce((n, d) => n + d.rows, 0)) : '—'} hint="across all sheets" />
        <KpiCard label="Sheets" value={datasets ? ready.reduce((n, d) => n + d.tables, 0) : '—'} hint="each one a table" />
        <KpiCard label="Conversations" value={datasets ? datasets.reduce((n, d) => n + d.threads, 0) : '—'} hint="kept across sessions" />
      </div>

      <SectionHeader title="All datasets" count={datasets?.length} right={loading ? 'Updating live' : undefined} />
      {datasets === null && !datasetsError ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 rounded-xl" />
          ))}
        </div>
      ) : datasets && datasets.length === 0 ? (
        <EmptyState
          icon={<FileSpreadsheet />}
          title="No datasets yet"
          hint={
            <>
              Upload an .xlsx workbook, drop one anywhere on this page, or run{' '}
              <code className="font-mono text-foreground">python manage.py load_sample</code> for a ready-made one.
            </>
          }
          action={
            <Button onClick={() => openUpload()}>
              <Upload /> Upload workbook
            </Button>
          }
        />
      ) : (
        datasets && <DatasetsTable datasets={datasets} />
      )}
    </Page>
  )
}
