import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import type { Block } from '@/lib/api'
import { formatAxis, formatValue } from '@/lib/format'

type ChartBlock = Extract<Block, { type: 'bar_chart' | 'line_chart' }>
const COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)']

const human = (s: string) => s.replace(/_/g, ' ')

// Rows arrive long ({x, y, series}); a grouped chart needs them wide ({x, [series]: y}).
function pivot(block: ChartBlock) {
  if (!block.series) return { data: block.rows, keys: [block.y] }
  const byX = new Map<string, Record<string, unknown>>()
  const keys: string[] = []
  for (const row of block.rows) {
    const x = String(row[block.x])
    const key = String(row[block.series])
    if (!keys.includes(key)) keys.push(key)
    byX.set(x, { ...(byX.get(x) ?? { [block.x]: row[block.x] }), [key]: row[block.y] })
  }
  return { data: [...byX.values()], keys }
}

function ChartTooltip({ active, payload, label, format }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string; format: ChartBlock['format'] }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex items-center gap-2 tabular-nums">
          <span className="size-2 rounded-full" style={{ background: p.color }} />
          {payload.length > 1 && <span className="text-muted-foreground">{p.name}</span>}
          <span className="font-medium">{formatValue(p.value, format)}</span>
        </p>
      ))}
    </div>
  )
}

export function ChartBlockView({ block }: { block: ChartBlock }) {
  const { data, keys } = pivot(block)
  const longLabels = data.some((d) => String(d[block.x]).length > 12)
  const horizontal = block.type === 'bar_chart' && (data.length > 8 || longLabels) && keys.length === 1
  const height = horizontal ? Math.max(220, data.length * 30 + 40) : 280
  const axis = { tick: { fontSize: 11, fill: 'var(--muted-foreground)' }, tickLine: false, axisLine: false }
  const tooltip = <Tooltip cursor={{ fill: 'var(--muted)', opacity: 0.5 }} content={<ChartTooltip format={block.format} />} />
  const legend = keys.length > 1 && <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />

  return (
    <div className="rounded-xl border bg-card p-4 pt-3">
      <p className="mb-3 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{human(block.y)}</span> by {human(block.x)}
        {block.series && <> and {human(block.series)}</>}
      </p>
      <ResponsiveContainer width="100%" height={height}>
        {block.type === 'line_chart' ? (
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey={block.x} {...axis} minTickGap={16} />
            <YAxis {...axis} width={56} tickFormatter={(v) => formatAxis(v, block.format)} />
            {tooltip}
            {legend}
            {keys.map((k, i) => (
              <Line key={k} dataKey={k} type="monotone" stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={data.length < 30} />
            ))}
          </LineChart>
        ) : horizontal ? (
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid horizontal={false} stroke="var(--border)" />
            <XAxis type="number" {...axis} tickFormatter={(v) => formatAxis(v, block.format)} />
            <YAxis type="category" dataKey={block.x} {...axis} width={120} />
            {tooltip}
            <Bar dataKey={keys[0]} fill={COLORS[0]} radius={[0, 4, 4, 0]} maxBarSize={22} />
          </BarChart>
        ) : (
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey={block.x} {...axis} />
            <YAxis {...axis} width={56} tickFormatter={(v) => formatAxis(v, block.format)} />
            {tooltip}
            {legend}
            {keys.map((k, i) => (
              <Bar key={k} dataKey={k} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} maxBarSize={48} />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
