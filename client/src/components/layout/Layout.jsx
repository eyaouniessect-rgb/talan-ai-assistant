import { useState, useEffect } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import Sidebar from './Sidebar'
import { Bell, Menu, Search, Calendar, X, AlertTriangle } from 'lucide-react'
import { useAuthStore, useNotifStore } from '../../store'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function GoogleCalendarBanner({ token, onDismiss }) {
  const [status, setStatus] = useState(null) // null | object
  const nav = useNavigate()

  useEffect(() => {
    if (!token) return
    fetch(`${API_BASE}/auth/google/status`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.json())
      .then(setStatus)
      .catch(() => {})
  }, [token])

  // Pas de bannière si statut inconnu ou si déjà connecté (sans révocation)
  if (!status) return null
  if (status.connected && !status.needs_reconnect) return null

  const isRevoked   = status.needs_reconnect
  const bgClass     = isRevoked ? 'bg-amber-50 border-amber-200' : 'bg-cyan/5 border-cyan/20'
  const iconClass   = isRevoked ? 'text-amber-500' : 'text-cyan'
  const textClass   = isRevoked ? 'text-amber-800' : 'text-navy'
  const subClass    = isRevoked ? 'text-amber-600' : 'text-slate-500'
  const btnClass    = isRevoked
    ? 'bg-amber-500 hover:bg-amber-600 text-white'
    : 'bg-cyan hover:bg-cyan/90 text-white'

  const message = isRevoked
    ? 'La connexion Google Calendar a expiré. Reconnectez votre compte pour continuer à gérer votre agenda.'
    : 'Connectez votre Google Calendar pour utiliser les fonctions agenda de l\'assistant.'

  return (
    <div className={`border-b px-5 py-2.5 flex items-center gap-3 shrink-0 ${bgClass}`}>
      {isRevoked
        ? <AlertTriangle size={16} className={iconClass + ' shrink-0'} />
        : <Calendar size={16} className={iconClass + ' shrink-0'} />
      }
      <span className={`text-xs flex-1 ${subClass}`}>{message}</span>
      <button
        onClick={() => nav('/settings')}
        className={`text-xs px-3 py-1.5 rounded-lg font-medium shrink-0 transition-colors ${btnClass}`}
      >
        {isRevoked ? 'Reconnecter' : 'Connecter Google Calendar'}
      </button>
      <button
        onClick={onDismiss}
        className="text-slate-400 hover:text-slate-600 shrink-0 transition-colors"
      >
        <X size={14} />
      </button>
    </div>
  )
}

const PAGE_TITLES = {
  '/dashboard': 'Dashboard',
  '/chat': 'Chat',
  '/historique': 'Historique',
  '/notifications': 'Notifications',
  '/settings': 'Paramètres',
  '/nouveau-projet': 'Nouveau Projet',
}

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [bannerDismissed, setBannerDismissed] = useState(false)
  const location = useLocation()
  const user  = useAuthStore(s => s.user)
  const token = useAuthStore(s => s.token)
  const notifications = useNotifStore(s => s.notifications)
  const unread = notifications.filter(n=>!n.read).length
  const nav = useNavigate()

  const title = PAGE_TITLES[location.pathname] || 'Talan Assistant'

  // Réinitialise la bannière quand l'utilisateur change de compte
  useEffect(() => {
    setBannerDismissed(false)
  }, [user?.id])

  // Masquer la bannière sur la page Settings (l'utilisateur est déjà en train de configurer)
  const showBanner = !bannerDismissed
    && user?.role !== 'rh'
    && location.pathname !== '/settings'

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      <Sidebar open={sidebarOpen} onClose={()=>setSidebarOpen(false)}/>

      {/* Main */}
      <div className="flex-1 flex flex-col lg:ml-64 min-w-0">
        {/* Topbar */}
        <header className="h-16 bg-white border-b border-slate-100 flex items-center px-5 gap-4 shrink-0">
          <button onClick={()=>setSidebarOpen(true)} className="lg:hidden text-slate-500 hover:text-slate-700">
            <Menu size={22}/>
          </button>

          <h1 className="font-display font-bold text-navy text-xl">{title}</h1>

          <div className="flex-1 max-w-sm ml-4 hidden md:block">
            <div className="relative">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/>
              <input className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-4 py-2 text-sm outline-none focus:border-cyan focus:ring-2 focus:ring-cyan/10 placeholder:text-slate-400"
                placeholder="Rechercher..." />
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <button onClick={()=>nav('/notifications')} className="relative w-9 h-9 flex items-center justify-center text-slate-500 hover:text-navy hover:bg-slate-100 rounded-xl transition-colors">
              <Bell size={19}/>
              {unread>0 && <span className="notification-dot"/>}
            </button>
            <div className="w-9 h-9 bg-navy rounded-xl flex items-center justify-center cursor-pointer">
              <span className="text-white text-xs font-bold">{user?.initials}</span>
            </div>
          </div>
        </header>

        {/* Bannière Google Calendar — si non connecté et pas sur /settings */}
        {showBanner && (
          <GoogleCalendarBanner
            token={token}
            onDismiss={() => setBannerDismissed(true)}
          />
        )}

        <main className="flex-1 overflow-auto">
          <Outlet/>
        </main>
      </div>
    </div>
  )
}
