import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, type DatasetStatus, type DatasetSummary } from '@/lib/api'

const POLL_MS = 1500

export const isLoading = (s: DatasetStatus) => s === 'queued' || s === 'loading' || s === 'describing'

interface AppData {
  datasets: DatasetSummary[] | null
  datasetsError: string | null
  refreshDatasets: () => Promise<void>
  addDataset: (d: DatasetSummary) => void
  // Bumped whenever a chat is created or answered, so the sidebar re-reads its thread list.
  threadsVersion: number
  bumpThreads: () => void
  // The upload dialog is opened from the sidebar, the dashboard, and by dropping a file anywhere.
  upload: { open: boolean; file: File | null }
  openUpload: (file?: File) => void
  closeUpload: () => void
}

const Ctx = createContext<AppData | null>(null)

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null)
  const [datasetsError, setError] = useState<string | null>(null)
  const [threadsVersion, setThreadsVersion] = useState(0)
  const [upload, setUpload] = useState<{ open: boolean; file: File | null }>({ open: false, file: null })

  const refreshDatasets = useCallback(async () => {
    try {
      setDatasets(await api.datasets())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    refreshDatasets()
  }, [refreshDatasets])

  // Poll only while something is loading.
  const anyLoading = datasets?.some((d) => isLoading(d.status)) ?? false
  useEffect(() => {
    if (!anyLoading) return
    const timer = setInterval(refreshDatasets, POLL_MS)
    return () => clearInterval(timer)
  }, [anyLoading, refreshDatasets])

  const value = useMemo<AppData>(
    () => ({
      datasets,
      datasetsError,
      refreshDatasets,
      addDataset: (d) => setDatasets((current) => [d, ...(current ?? [])]),
      threadsVersion,
      bumpThreads: () => setThreadsVersion((v) => v + 1),
      upload,
      openUpload: (file) => setUpload({ open: true, file: file ?? null }),
      closeUpload: () => setUpload({ open: false, file: null }),
    }),
    [datasets, datasetsError, refreshDatasets, threadsVersion, upload],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAppData() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAppData must be used inside AppDataProvider')
  return ctx
}
