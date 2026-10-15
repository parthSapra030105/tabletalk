import { Navigate, Route, Routes } from 'react-router-dom'

import ChatPage from '@/pages/Chat'
import DashboardPage from '@/pages/Dashboard'
import DatasetPage from '@/pages/Dataset'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/datasets/:datasetId" element={<DatasetPage />} />
      <Route path="/datasets/:datasetId/chat" element={<ChatPage />} />
      <Route path="/datasets/:datasetId/chat/:threadId" element={<ChatPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
