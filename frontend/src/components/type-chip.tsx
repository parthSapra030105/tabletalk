import { Calendar, Hash, ToggleLeft, Type } from 'lucide-react'

const TYPES: Record<string, { label: string; icon: typeof Hash }> = {
  numeric: { label: 'number', icon: Hash },
  date: { label: 'date', icon: Calendar },
  timestamp: { label: 'date-time', icon: Calendar },
  boolean: { label: 'yes/no', icon: ToggleLeft },
  text: { label: 'text', icon: Type },
}

export function TypeChip({ type }: { type: string }) {
  const t = TYPES[type] ?? TYPES.text
  const Icon = t.icon
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
      <Icon className="size-3" />
      {t.label}
    </span>
  )
}
