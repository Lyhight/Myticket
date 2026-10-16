import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './state/AuthContext'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import TicketsPage from './pages/TicketsPage'
import TicketPage from './pages/TicketPage'
import ReviewPage from './pages/ReviewPage'
import KnowledgePage from './pages/KnowledgePage'

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <div className="boot"><div className="loader"/><span>正在连接 MyTicket Agent...</span></div>
  if (!user) return <Routes><Route path="*" element={<LoginPage />} /></Routes>
  return (
    <Layout>
      <Routes>
        <Route path="/tickets" element={<TicketsPage />} />
        <Route path="/tickets/:id" element={<TicketPage />} />
        <Route path="/review" element={user.role === 'admin' ? <ReviewPage /> : <Navigate to="/tickets" />} />
        <Route path="/knowledge" element={user.role === 'admin' ? <KnowledgePage /> : <Navigate to="/tickets" />} />
        <Route path="*" element={<Navigate to="/tickets" replace />} />
      </Routes>
    </Layout>
  )
}
