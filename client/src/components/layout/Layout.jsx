import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import { Bell, Menu, Search } from 'lucide-react'
import { useAuthStore, useNotifStore } from '../../store'
import { useNavigate } from 'react-router-dom'

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
  const location = useLocation()
  const user = useAuthStore(s => s.user)
  const notifications = useNotifStore(s => s.notifications)
  const unread = notifications.filter(n=>!n.read).length
  const nav = useNavigate()

  const title = PAGE_TITLES[location.pathname] || 'Talan Assistant'

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

        <main className="flex-1 overflow-auto">
          <Outlet/>
        </main>
      </div>
    </div>
  )
}
