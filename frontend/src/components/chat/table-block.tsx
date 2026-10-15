import { ArrowDown, ArrowUp, Download } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { formatValue } from '@/lib/format'
import { cn } from '@/lib/utils'

type Cell = string | number | boolean | null

function exportCsv(columns: string[], rows: Cell[][]) {
  const escape = (v: Cell) => {
    const s = v === null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [columns, ...rows].map((r) => r.map(escape).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: 'tabletalk-result.csv' })
  a.click()
  URL.revokeObjectURL(url)
}

export function TableBlockView({ columns, rows }: { columns: string[]; rows: Cell[][] }) {
  const [sort, setSort] = useState<{ col: number; dir: 1 | -1 } | null>(null)
  const numeric = useMemo(() => columns.map((_, i) => rows.length > 0 && rows.every((r) => r[i] === null || typeof r[i] === 'number')), [columns, rows])

  const sorted = useMemo(() => {
    if (!sort) return rows
    return [...rows].sort((a, b) => {
      const x = a[sort.col]
      const y = b[sort.col]
      if (x === y) return 0
      if (x === null) return 1
      if (y === null) return -1
      return (x < y ? -1 : 1) * sort.dir
    })
  }, [rows, sort])

  function toggle(col: number) {
    setSort((s) => (s?.col !== col ? { col, dir: -1 } : s.dir === -1 ? { col, dir: 1 } : null))
  }

  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div className="max-h-80 overflow-auto scrollbar-slim">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-muted/90 backdrop-blur">
            <tr>
              {columns.map((c, i) => (
                <th key={c} className={cn('whitespace-nowrap px-3 py-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground', numeric[i] ? 'text-right' : 'text-left')}>
                  <button onClick={() => toggle(i)} className="inline-flex items-center gap-1 hover:text-foreground">
                    {c.replace(/_/g, ' ')}
                    {sort?.col === i && (sort.dir === -1 ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, r) => (
              <tr key={r} className="border-t border-border-subtle hover:bg-muted/30">
                {row.map((v, i) => (
                  <td key={i} className={cn('whitespace-nowrap px-3 py-2', numeric[i] && 'text-right tabular-nums')}>
                    {v === null ? <span className="text-faint">—</span> : typeof v === 'number' ? formatValue(v, 'number') : String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t px-3 py-1.5 text-xs text-muted-foreground">
        <span className="tabular-nums">
          {rows.length.toLocaleString('en-IN')} row{rows.length === 1 ? '' : 's'}
        </span>
        <Button variant="ghost" size="xs" onClick={() => exportCsv(columns, rows)}>
          <Download /> CSV
        </Button>
      </div>
    </div>
  )
}
