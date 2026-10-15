import { AlertCircle } from 'lucide-react'

import { AppShell } from '@/components/app-shell'
import { DatasetCard } from '@/components/dataset-card'
import { UploadCard } from '@/components/upload-card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { useDatasets } from '@/hooks/use-datasets'

export default function DashboardPage() {
  const { datasets, error, refresh, setDatasets } = useDatasets()

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">Your data</h1>
            <p className="text-muted-foreground">
              Upload an Excel workbook and ask questions about it in plain language. Every number in an answer comes from
              a query you can inspect.
            </p>
          </div>

          <UploadCard onUploaded={(d) => setDatasets((current) => [d, ...(current ?? [])])} />

          {error && (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertTitle>Couldn't load your datasets</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <section className="space-y-3">
            <h2 className="text-sm font-medium text-muted-foreground">Datasets</h2>
            {datasets === null && !error ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-44 rounded-xl" />
                ))}
              </div>
            ) : datasets && datasets.length === 0 ? (
              <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                No datasets yet. Upload a workbook above, or run <code className="font-mono">python manage.py load_sample</code>.
              </p>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {datasets?.map((d) => <DatasetCard key={d.id} dataset={d} onDeleted={refresh} />)}
              </div>
            )}
          </section>
        </div>
      </div>
    </AppShell>
  )
}
