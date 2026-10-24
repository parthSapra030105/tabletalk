import { Menu, Table2, UploadCloud } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { Sidebar } from '@/components/layout/sidebar'
import { UploadDialog } from '@/components/upload-dialog'
import { Button } from '@/components/ui/button'
import { useAppData } from '@/context/app-data'

// Sidebar on large screens, a drawer on small ones, and a drop target covering the whole window.
export function AppShell({ children }: { children: ReactNode }) {
  const { openUpload } = useAppData()
  const [drawer, setDrawer] = useState(false)
  const [dragging, setDragging] = useState(false)
  const depth = useRef(0)
  const location = useLocation()

  useEffect(() => setDrawer(false), [location.pathname])

  useEffect(() => {
    const hasFile = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files')
    const enter = (e: DragEvent) => {
      if (!hasFile(e)) return
      depth.current += 1
      setDragging(true)
    }
    const leave = () => {
      depth.current = Math.max(0, depth.current - 1)
      if (depth.current === 0) setDragging(false)
    }
    const over = (e: DragEvent) => hasFile(e) && e.preventDefault()
    // Capture phase: runs even when the upload dialog's own drop zone stops the event from bubbling.
    const reset = () => {
      depth.current = 0
      setDragging(false)
    }
    const drop = (e: DragEvent) => {
      if (!hasFile(e)) return
      e.preventDefault()
      const file = e.dataTransfer?.files[0]
      if (file) openUpload(file)
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragleave', leave)
    window.addEventListener('dragover', over)
    window.addEventListener('drop', reset, true)
    window.addEventListener('dragend', reset)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('dragover', over)
      window.removeEventListener('drop', reset, true)
      window.removeEventListener('dragend', reset)
      window.removeEventListener('drop', drop)
    }
  }, [openUpload])

  return (
    <div className="flex h-dvh">
      <aside className="hidden w-64 shrink-0 border-r border-sidebar-border lg:block">
        <Sidebar />
      </aside>

      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/30 animate-in fade-in" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 border-r border-sidebar-border shadow-xl animate-in slide-in-from-left duration-200">
            <Sidebar onNavigate={() => setDrawer(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-background/95 px-4 backdrop-blur lg:hidden">
          <Button variant="ghost" size="icon-sm" onClick={() => setDrawer(true)} aria-label="Open menu">
            <Menu />
          </Button>
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Table2 className="size-3.5" />
            </span>
            Tabletalk
          </Link>
        </header>
        <main className="min-h-0 flex-1">{children}</main>
      </div>

      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-background/70 backdrop-blur-sm animate-in fade-in">
          <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-primary bg-card px-12 py-10 shadow-xl">
            <UploadCloud className="size-8 text-primary" />
            <p className="font-medium">Drop to upload this workbook</p>
          </div>
        </div>
      )}

      <UploadDialog />
    </div>
  )
}
