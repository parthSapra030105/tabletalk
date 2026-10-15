import { Check, ChevronRight, Code2, Copy } from 'lucide-react'
import { Fragment, useState } from 'react'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

const KEYWORDS = /\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|JOIN|LEFT JOIN|INNER JOIN|ON|AS|AND|OR|NOT|IN|IS|NULL|CASE|WHEN|THEN|ELSE|END|WITH|UNION ALL|UNION|DISTINCT|DESC|ASC|OVER|PARTITION BY|BETWEEN|INTERVAL|FILTER)\b/g
const BREAKS = /\s+(FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|LEFT JOIN|INNER JOIN|JOIN|UNION ALL|UNION)\s+/g

// One clause per line and keywords in the accent colour: enough to read a query at a glance.
function pretty(sql: string) {
  return sql.replace(BREAKS, '\n$1 ').replace(/\),\s*(\w+ AS \()/g, '),\n$1')
}

function highlight(line: string) {
  const parts = line.split(KEYWORDS)
  return parts.map((p, i) => (i % 2 === 1 ? <span key={i} className="text-primary">{p}</span> : <Fragment key={i}>{p}</Fragment>))
}

export function SqlBlockView({ query }: { query: string }) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  async function copy() {
    await navigator.clipboard.writeText(query)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-xl border bg-card">
      <div className="flex items-center">
        <CollapsibleTrigger className="flex flex-1 items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">
          <ChevronRight className={cn('size-3.5 transition-transform', open && 'rotate-90')} />
          <Code2 className="size-3.5" />
          SQL that ran
          <span className="font-normal text-faint">· read-only</span>
        </CollapsibleTrigger>
        <button onClick={copy} className="mr-1.5 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Copy SQL">
          {copied ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
        </button>
      </div>
      <CollapsibleContent>
        <pre className="overflow-x-auto border-t bg-muted/30 px-4 py-3 font-mono text-xs leading-relaxed scrollbar-slim">
          {pretty(query)
            .split('\n')
            .map((line, i) => (
              <div key={i}>{highlight(line)}</div>
            ))}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  )
}
