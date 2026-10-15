import { Navigate, Outlet, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/app-shell'
import ChatPage from '@/pages/Chat'
import DashboardPage from '@/pages/Dashboard'
import DatasetPage from '@/pages/Dataset'

// One shell for every page, so the sidebar stays mounted while only the page changes.
function ShellLayout() {
  return (
    <AppShell>
      <Outlet />
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
