import { NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore, useNotifStore } from '../../store'
import { LayoutDashboard, MessageSquare, Clock, Bell, Settings, Rocket, LogOut, Zap, X, ShieldCheck } from 'lucide-react'
import clsx from 'clsx'

const NAV = [
  { to:'/dashboard', icon:LayoutDashboard, label:'Dashboard' },
  { to:'/chat', icon:MessageSquare, label:'Chat' },
  { to:'/historique', icon:Clock, label:'Historique' },
  { to:'/notifications', icon:Bell, label:'Notifications', notif:true },
  { to:'/settings', icon:Settings, label:'Paramètres' },
]

export default function Sidebar({ open, onClose }) {
  const user = useAuthStore(s => s.user)
  const logout = useAuthStore(s => s.logout)
  const notifications = useNotifStore(s => s.notifications)
  const unread = notifications.filter(n=>!n.read).length
  const nav = useNavigate()
  const isPM = user?.role === 'pm'
  const isRH = user?.role === 'rh'

  const handleLogout = () => { logout(); nav('/') }

  return (
    <>
      {/* Overlay mobile */}
      {open && <div className="fixed inset-0 bg-black/20 z-20 lg:hidden" onClick={onClose}/>}

      <aside className={clsx(
        'fixed top-0 left-0 h-full w-64 bg-white border-r border-slate-100 z-30',
        'flex flex-col transition-transform duration-300',
        open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
      )}>
        {/* Logo */}
        <div className="flex items-center justify-between px-5 py-5 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-navy rounded-lg flex items-center justify-center">
              <Zap size={15} className="text-cyan" />
            </div>
            <div>
              <div className="font-display font-bold text-navy text-base leading-tight">TALAN</div>
              <div className="text-xs text-slate-400 leading-tight">Assistant IA</div>
            </div>
          </div>
          <button onClick={onClose} className="lg:hidden text-slate-400 hover:text-slate-600 p-1">
            <X size={18}/>
          </button>
        </div>

        {/* User */}
        <div className="px-4 py-4 border-b border-slate-100">
          <div className="flex items-center gap-3 p-2.5 bg-slate-50 rounded-xl">
            <div className="w-9 h-9 bg-navy rounded-xl flex items-center justify-center shrink-0">
              <span className="text-white text-xs font-bold">{user?.initials}</span>
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-slate-800 truncate">{user?.name}</div>
              <span className={isPM ? 'badge-pm' : isRH ? 'badge-rh' : 'badge-consultant'}>
                {isPM ? 'Project Manager' : isRH ? 'RH' : 'Consultant'}
              </span>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
          {NAV.map(({ to, icon:Icon, label, notif }) => (
            <NavLink key={to} to={to} onClick={onClose}
              className={({isActive}) => clsx('sidebar-item', isActive && 'active')}>
              <Icon size={18} className="shrink-0"/>
              <span className="flex-1">{label}</span>
              {notif && unread > 0 && (
                <span className="bg-red-500 text-white text-xs w-5 h-5 rounded-full flex items-center justify-center font-medium">
                  {unread}
                </span>
              )}
            </NavLink>
          ))}

          {isPM && (
            <NavLink to="/nouveau-projet" onClick={onClose}
              className={({isActive}) => clsx('sidebar-item mt-2', isActive && 'active')}>
              <Rocket size={18} className="shrink-0"/>
              <span className="flex-1">Nouveau Projet</span>
              <span className="text-xs bg-cyan/10 text-cyan px-1.5 py-0.5 rounded-md font-medium">PM</span>
            </NavLink>
          )}

          {isRH && (
            <NavLink to="/rh" onClick={onClose}
              className={({isActive}) => clsx('sidebar-item mt-2', isActive && 'active')}>
              <ShieldCheck size={18} className="shrink-0"/>
              <span className="flex-1">Espace RH</span>
              <span className="text-xs bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-md font-medium">RH</span>
            </NavLink>
          )}
        </nav>

        {/* Logout */}
        <div className="px-3 py-3 border-t border-slate-100">
          <button onClick={handleLogout}
            className="sidebar-item w-full text-red-500 hover:bg-red-50 hover:text-red-600">
            <LogOut size={18}/>
            <span>Déconnexion</span>
          </button>
        </div>
      </aside>
    </>
  )
}
