// Typed client for the Django API. Shapes mirror backend/api/views.py.

export type DatasetStatus = 'queued' | 'loading' | 'describing' | 'ready' | 'failed'

export interface DatasetSummary {
  id: number
  name: string
  status: DatasetStatus
  progress: { sheet?: string; rows?: number; total?: number }
  error: string
  is_sample: boolean
  created_at: string
  file_size: number
  tables: number
  rows: number
  threads: number
}

export interface SheetReport {
  sheet: string
  table: string | null
  status: 'loaded' | 'skipped'
  reason: string | null
  header_row: number | null
  rows_loaded: number
  skipped_rows: Record<string, { count: number; examples: number[] }>
  columns: {
    name: string
    original: string | null
    type: string
    nulls: number
    coercion_failures: number
    failure_examples: [number, unknown][]
    note: string | null
  }[]
}

export interface CatalogTable {
  name: string
  rows: number
  description: string
  ambiguities: { columns: string[]; note: string }[]
  columns: { name: string; original: string | null; type: string; description: string }[]
}

export interface Join {
  from_table: string
  from_column: string
  to_table: string
  to_column: string
  overlap: number
  one_to_one: boolean
}

export interface DatasetDetail extends DatasetSummary {
  timings: { load_seconds?: number; describe_seconds?: number; catalog?: Record<string, number> }
  sheets: SheetReport[]
  catalog: { tables: CatalogTable[]; joins: Join[] }
}

export type ValueFormat = 'inr' | 'number' | 'percent' | 'date' | 'text'
type Cell = string | number | boolean | null

// The blocks the backend sends. Anything else is shown by a fallback, never crashes the page.
export type Block =
  | { type: 'text'; content: string }
  | { type: 'notice'; content: string }
  | { type: 'metric'; label: string; value: number | null; format: ValueFormat; display: string }
  | { type: 'bar_chart' | 'line_chart'; x: string; y: string; series: string | null; format: ValueFormat; rows: Record<string, Cell>[] }
  | { type: 'table'; columns: string[]; rows: Cell[][] }
  | { type: 'sql'; query: string }
  | { type: 'suggestions'; options: string[] }

export interface Usage {
  purpose: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  seconds: number
}

export interface Message {
  id: number
  question: string
  blocks: Block[]
  route: string
  sql: string
  total_tokens: number
  seconds: number
  created_at: string
  usage: Usage[]
}

export interface ThreadSummary {
  id: string
  title: string
  updated_at: string
  messages: number
}

export interface ThreadDetail {
  id: string
  title: string
  dataset: number
  messages: Message[]
}

export interface GlossaryEntry {
  term: string
  meaning: string
  columns: string[]
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, init)
  } catch {
    throw new ApiError('Cannot reach the server. Is the backend running?', 0)
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(body?.error ?? `The server returned ${response.status}.`, response.status)
  }
  return body as T
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  datasets: () => request<DatasetSummary[]>('/datasets/'),
  dataset: (id: number) => request<DatasetDetail>(`/datasets/${id}/`),
  deleteDataset: (id: number) => request<{ deleted: number }>(`/datasets/${id}/`, { method: 'DELETE' }),
  // XHR rather than fetch: only XHR reports how much of a large file has been sent.
  upload: (file: File, name: string | undefined, onProgress: (fraction: number) => void) =>
    new Promise<DatasetSummary>((resolve, reject) => {
      const form = new FormData()
      form.append('file', file)
      if (name) form.append('name', name)
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/datasets/')
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
      xhr.onerror = () => reject(new ApiError('Cannot reach the server. Is the backend running?', 0))
      xhr.onload = () => {
        let body: { error?: string } | null = null
        try {
          body = JSON.parse(xhr.responseText)
        } catch {
          // non-JSON error page
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as DatasetSummary)
        else reject(new ApiError(body?.error ?? `The server returned ${xhr.status}.`, xhr.status))
      }
      xhr.send(form)
    }),
  threads: (datasetId: number) => request<ThreadSummary[]>(`/datasets/${datasetId}/threads/`),
  newThread: (datasetId: number) => request<ThreadDetail>(`/datasets/${datasetId}/threads/`, { method: 'POST' }),
  thread: (id: string) => request<ThreadDetail>(`/threads/${id}/`),
  deleteThread: (id: string) => request<{ deleted: string }>(`/threads/${id}/`, { method: 'DELETE' }),
  ask: (threadId: string, question: string) => request<Message>(`/threads/${threadId}/messages/`, json({ question })),
  glossary: (datasetId: number) => request<GlossaryEntry[]>(`/datasets/${datasetId}/glossary/`),
  deleteGlossaryEntry: (datasetId: number, term: string) =>
    request<{ deleted: string }>(`/datasets/${datasetId}/glossary/${encodeURIComponent(term)}/`, { method: 'DELETE' }),
}
