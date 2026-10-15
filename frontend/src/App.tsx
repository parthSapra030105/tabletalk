import { lazy, Suspense } from 'react'
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/app-shell'
import DashboardPage from '@/pages/Dashboard'
import DatasetPage from '@/pages/Dataset'

// The chat page carries the chart library; load it only when a chat is opened.
const ChatPage = lazy(() => import('@/pages/Chat'))

// One shell for every page, so the sidebar stays mounted while only the page changes.
function ShellLayout() {
  return (
    <AppShell>
      <Suspense fallback={null}>
        <Outlet />
      </Suspense>
    </AppShell>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<ShellLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/datasets/:datasetId" element={<DatasetPage />} />
        <Route path="/datasets/:datasetId/chat" element={<ChatPage />} />
        <Route path="/datasets/:datasetId/chat/:threadId" element={<ChatPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
