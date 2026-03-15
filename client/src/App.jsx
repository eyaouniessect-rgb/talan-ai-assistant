import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store'
import Login from './pages/Login'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import { Historique, Notifications, NouveauProjet, Settings } from './pages/OtherPages'

function ProtectedRoute({ children }) {
  const user = useAuthStore(s => s.user)
  return user ? children : <Navigate to="/" replace />
}

export default function App() {
  const user = useAuthStore(s => s.user)

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={user ? <Navigate to="/dashboard"/> : <Login/>}/>
        <Route path="/" element={<ProtectedRoute><Layout/></ProtectedRoute>}>
          <Route path="dashboard" element={<Dashboard/>}/>
          <Route path="chat" element={<Chat/>}/>
          <Route path="historique" element={<Historique/>}/>
          <Route path="notifications" element={<Notifications/>}/>
          <Route path="nouveau-projet" element={<NouveauProjet/>}/>
          <Route path="settings" element={<Settings/>}/>
        </Route>
        <Route path="*" element={<Navigate to="/" replace/>}/>
      </Routes>
    </BrowserRouter>
  )
}
