// src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store'
import Login from './pages/Login'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import Historique from './pages/Historique'
import Notifications from './pages/Notifications'
import NouveauProjet from './pages/NouveauProjet'
import Settings from './pages/Settings'
import RHPage from './pages/rh/RHPage'

function ProtectedRoute({ children }) {
  const user = useAuthStore(s => s.user)
  return user ? children : <Navigate to="/" replace />
}

function RHRoute({ children }) {
  const user = useAuthStore(s => s.user)
  if (!user) return <Navigate to="/" replace />
  if (user.role !== 'rh') return <Navigate to="/dashboard" replace />
  return children
}

export default function App() {
  const user = useAuthStore(s => s.user)

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={user ? <Navigate to={user.role === 'rh' ? '/rh' : '/dashboard'} /> : <Login />} />
        <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="chat" element={<Chat />} />
          <Route path="historique" element={<Historique />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="nouveau-projet" element={<NouveauProjet />} />
          <Route path="settings" element={<Settings />} />
          <Route path="rh" element={<RHRoute><RHPage /></RHRoute>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}