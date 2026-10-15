// Display formatting. Mirrors backend/agent/answer.py fmt(), so a number reads the same in
// the answer text, the metric cards, the chart axes and the table.
import type { ValueFormat } from './api'

function indianGrouping(n: number, decimals = 2): string {
  const sign = n < 0 ? '-' : ''
  const [whole, frac] = Math.abs(n).toFixed(decimals).split('.')
  const tail = whole.slice(-3)
  let head = whole.slice(0, -3)
  const groups: string[] = []
  while (head.length > 2) {
    groups.unshift(head.slice(-2))
    head = head.slice(0, -2)
  }
  const grouped = [...(head ? [head] : []), ...groups, tail].join(',')
  return sign + grouped + (frac && Number(frac) !== 0 ? `.${frac}` : '')
}

export function formatValue(value: unknown, format: ValueFormat = 'number'): string {
  if (value === null || value === undefined) return '—'
  if (typeof value !== 'number') return String(value)
  if (format === 'inr') {
    if (Math.abs(value) >= 1e7) return `₹${(value / 1e7).toFixed(2)} Cr`
    if (Math.abs(value) >= 1e5) return `₹${(value / 1e5).toFixed(2)} L`
    return `₹${indianGrouping(value)}`
  }
  if (format === 'percent') return `${value.toFixed(1)}%`
  return Math.abs(value) >= 1000 ? indianGrouping(value) : String(Number.isInteger(value) ? value : +value.toFixed(2))
}

// Compact axis labels: ₹4.8Cr, ₹12L, 1.2k.
export function formatAxis(value: number, format: ValueFormat): string {
  const prefix = format === 'inr' ? '₹' : ''
  const abs = Math.abs(value)
  if (abs >= 1e7) return `${prefix}${+(value / 1e7).toFixed(1)}Cr`
  if (abs >= 1e5) return `${prefix}${+(value / 1e5).toFixed(1)}L`
  if (abs >= 1e3) return `${prefix}${+(value / 1e3).toFixed(1)}k`
  return `${prefix}${value}`
}

export function formatCount(n: number): string {
  return indianGrouping(n, 0)
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

// Short counts for tight spaces: 950, 10.2k, 1.0L, 2.5Cr (Indian units).
export function formatCompact(n: number): string {
  if (n >= 1e7) return `${+(n / 1e7).toFixed(1)}Cr`
  if (n >= 1e5) return `${+(n / 1e5).toFixed(1)}L`
  if (n >= 1e3) return `${+(n / 1e3).toFixed(1)}k`
  return String(n)
}
