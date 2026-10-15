import { useCallback, useEffect, useState } from 'react'

import { inProgress } from '@/components/status-badge'
import { api, type DatasetSummary } from '@/lib/api'

const POLL_MS = 1500

// The dataset list, refreshed every POLL_MS while any dataset is still loading.
export function useDatasets() {
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setDatasets(await api.datasets())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const loading = datasets?.some((d) => inProgress(d.status)) ?? false
  useEffect(() => {
    if (!loading) return
    const timer = setInterval(refresh, POLL_MS)
    return () => clearInterval(timer)
  }, [loading, refresh])

  return { datasets, error, refresh, setDatasets }
}
