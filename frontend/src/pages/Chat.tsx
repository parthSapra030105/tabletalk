import { AlertCircle, ArrowUp, Database, Info, Loader2, Plus, RotateCcw, Table2, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { AnswerBlocks, AnswerFooter } from '@/components/chat/answer'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useAppData } from '@/context/app-data'
import { api, type DatasetDetail, type Message, type ThreadDetail } from '@/lib/api'
import { formatCount } from '@/lib/format'

const human = (s: string) => s.replace(/_/g, ' ')

// A few concrete first questions built from the catalog, so an empty chat never starts blank.
function starters(d: DatasetDetail): string[] {
  const out = ["What's in this file?"]
  const main = [...d.catalog.tables].sort((a, b) => b.rows - a.rows)[0]
  if (!main) return out
  const date = main.columns.find((c) => c.type === 'date')
  const money = main.columns.find((c) => c.type === 'numeric' && /amount|sales|revenue|price|value|total|spend/.test(c.name))
  const group = main.columns.find((c) => c.type === 'text' && /region|category|city|segment|status|channel|state|type/.test(c.name))
  if (money && date) out.push(`Total ${human(money.name)} by month`)
  if (money && group) out.push(`Which ${human(group.name)} has the highest ${human(money.name)}?`)
  if (date) out.push(`How many ${human(main.name)} were there last quarter?`)
  return out.slice(0, 4)
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-[15px] text-primary-foreground sm:max-w-[75%]">{text}</p>
    </div>
  )
}

function AssistantMark() {
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
      <Table2 className="size-3.5" />
    </span>
  )
}

function Thinking() {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="flex gap-3">
      <AssistantMark />
      <div className="flex-1 space-y-3 pt-1">
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin text-primary" />
          Reading the question, picking columns, writing and checking the SQL
          <span className="tabular-nums text-faint">{seconds}s</span>
        </p>
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    </div>
  )
}

function Turn({ message, onAsk }: { message: Message; onAsk: (q: string) => void }) {
  return (
    <div className="space-y-5 animate-fade-up">
      <UserBubble text={message.question} />
      <div className="flex gap-3">
        <AssistantMark />
        <div className="min-w-0 flex-1 pt-0.5">
          <AnswerBlocks blocks={message.blocks} onAsk={onAsk} />
          <AnswerFooter message={message} />
        </div>
      </div>
    </div>
  )
}

export default function ChatPage() {
  const params = useParams()
  const datasetId = Number(params.datasetId)
  const threadId = params.threadId
  const navigate = useNavigate()
  const { bumpThreads, refreshDatasets } = useAppData()

  const [dataset, setDataset] = useState<DatasetDetail | null>(null)
  const [thread, setThread] = useState<ThreadDetail | null>(null)
  const [loadingThread, setLoadingThread] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const [failed, setFailed] = useState<{ question: string; error: string } | null>(null)
  const [draft, setDraft] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    api.dataset(datasetId).then(setDataset).catch((e) => toast.error((e as Error).message))
  }, [datasetId])

  useEffect(() => {
    setFailed(null)
    if (!threadId) return setThread(null)
    if (thread?.id === threadId) return // just created here; already in state
    setLoadingThread(true)
    api
      .thread(threadId)
      .then(setThread)
      .catch(() => navigate(`/datasets/${datasetId}/chat`, { replace: true }))
      .finally(() => setLoadingThread(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId, datasetId])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [thread?.messages.length, pending, failed])

  async function ask(question: string) {
    const q = question.trim()
    if (!q || pending) return
    setDraft('')
    setFailed(null)
    setPending(q)
    try {
      let current = thread
      if (!current) {
        current = await api.newThread(datasetId)
        setThread(current)
        navigate(`/datasets/${datasetId}/chat/${current.id}`, { replace: true })
      }
      const message = await api.ask(current.id, q)
      setThread((t) => (t ? { ...t, title: t.title || q, messages: [...t.messages, message] } : t))
      bumpThreads()
      refreshDatasets()
    } catch (e) {
      setFailed({ question: q, error: (e as Error).message })
    } finally {
      setPending(null)
      input.current?.focus()
    }
  }

  async function deleteThread() {
    if (!thread) return
    try {
      await api.deleteThread(thread.id)
      bumpThreads()
      setConfirmDelete(false)
      setThread(null)
      navigate(`/datasets/${datasetId}/chat`)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      ask(draft)
    }
  }

  const messages = thread?.messages ?? []
  const empty = !loadingThread && messages.length === 0 && !pending && !failed

  if (dataset && dataset.status !== 'ready') {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center">
        <div>
          <p className="font-medium">This dataset isn't ready to chat with yet.</p>
          <Button asChild variant="link">
            <Link to={`/datasets/${datasetId}`}>See its status</Link>
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4 sm:px-6">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{thread?.title || 'New chat'}</p>
          <p className="truncate text-xs text-muted-foreground">{dataset ? dataset.name : ' '}</p>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button asChild variant="ghost" size="icon-sm" className="text-muted-foreground">
              <Link to={`/datasets/${datasetId}`} aria-label="Dataset details">
                <Database />
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Columns, joins and load report</TooltipContent>
        </Tooltip>
        {thread && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-rose-600" onClick={() => setConfirmDelete(true)} aria-label="Delete chat">
                <Trash2 />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Delete chat</TooltipContent>
          </Tooltip>
        )}
        <Button variant="outline" size="sm" onClick={() => navigate(`/datasets/${datasetId}/chat`)} disabled={!thread}>
          <Plus /> New chat
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-slim">
        <div className="mx-auto max-w-3xl space-y-10 px-4 py-8 sm:px-6">
          {loadingThread && (
            <div className="space-y-4">
              <Skeleton className="ml-auto h-10 w-2/3 rounded-2xl" />
              <Skeleton className="h-32 rounded-xl" />
            </div>
          )}

          {empty && dataset && (
            <div className="flex flex-col items-center pt-10 text-center animate-fade-up sm:pt-16">
              <span className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
                <Table2 className="size-6" />
              </span>
              <h1 className="text-xl font-semibold tracking-tight">Ask anything about {dataset.name}</h1>
              <p className="mt-1.5 max-w-md text-sm text-muted-foreground">
                {dataset.catalog.tables.length} sheets · {formatCount(dataset.rows)} rows. Answers come from read-only queries, and the SQL
                behind every number is one click away.
              </p>
              <div className="mt-8 grid w-full max-w-xl gap-2 sm:grid-cols-2">
                {starters(dataset).map((s) => (
                  <button
                    key={s}
                    onClick={() => ask(s)}
                    className="rounded-xl border bg-card px-4 py-3 text-left text-sm transition-colors hover:border-primary/40 hover:bg-primary-soft"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => (
            <Turn key={m.id} message={m} onAsk={ask} />
          ))}

          {pending && (
            <div className="space-y-5">
              <UserBubble text={pending} />
              <Thinking />
            </div>
          )}

          {failed && (
            <div className="space-y-5">
              <UserBubble text={failed.question} />
              <div className="flex gap-3">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-rose-50 text-rose-600 dark:bg-rose-500/10">
                  <AlertCircle className="size-3.5" />
                </span>
                <div className="flex-1 space-y-2 pt-0.5">
                  <p className="text-sm">That question didn't go through: {failed.error}</p>
                  <Button size="sm" variant="outline" onClick={() => ask(failed.question)}>
                    <RotateCcw /> Try again
                  </Button>
                </div>
              </div>
            </div>
          )}
          <div ref={bottom} />
        </div>
      </div>

      <div className="shrink-0 px-4 pb-4 sm:px-6">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm transition-shadow focus-within:border-primary/50 focus-within:ring-3 focus-within:ring-primary/10">
            <Textarea
              ref={input}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKey}
              placeholder={dataset ? `Ask about ${dataset.name}…` : 'Ask a question…'}
              rows={1}
              maxLength={1000}
              className="max-h-40 min-h-9 resize-none border-0 bg-transparent px-2 py-1.5 text-[15px] shadow-none focus-visible:ring-0 dark:bg-transparent"
              autoFocus
            />
            <Button size="icon" onClick={() => ask(draft)} disabled={!draft.trim() || pending !== null} aria-label="Send">
              <ArrowUp />
            </Button>
          </div>
          <p className="mt-2 flex items-center justify-center gap-1.5 text-[11px] text-faint">
            <Info className="size-3" /> Read-only: this assistant can't change your data. Enter to send, Shift+Enter for a new line.
          </p>
        </div>
      </div>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this chat?</DialogTitle>
            <DialogDescription>The conversation and what the assistant remembers of it are removed. Your data isn't touched.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button variant="destructive" onClick={deleteThread}>
              Delete chat
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
