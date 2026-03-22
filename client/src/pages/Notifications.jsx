// src/pages/Notifications.jsx
import { useState } from 'react'
import { useNotifStore } from '../store'
import { Bell, CheckCheck, AlertTriangle, CheckCircle, Info, X } from 'lucide-react'
import clsx from 'clsx'

const NOTIF_ICONS = {
  info: <Info size={16} className="text-blue-500" />,
  success: <CheckCircle size={16} className="text-green-500" />,
  warning: <AlertTriangle size={16} className="text-amber-500" />,
  error: <X size={16} className="text-red-500" />,
}

const SOURCE_COLORS = {
  Jira: 'bg-orange-50 text-orange-700',
  Slack: 'bg-purple-50 text-purple-700',
  RH: 'bg-green-50 text-green-700',
  Calendar: 'bg-cyan-50 text-cyan-700',
  CRM: 'bg-blue-50 text-blue-700',
}

const TABS = ['Toutes', 'Non lues', 'Actions requises']

export default function Notifications() {
  const [tab, setTab] = useState('Toutes')
  const { notifications, markRead, markAllRead } = useNotifStore()

  const filtered = notifications.filter(n =>
    tab === 'Non lues' ? !n.read :
    tab === 'Actions requises' ? n.type === 'warning' : true
  )
  const unread = notifications.filter(n => !n.read).length

  return (
    <div className="p-6 max-w-2xl mx-auto">
      {/* Tabs + bouton tout marquer */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex gap-1">
          {TABS.map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={clsx('text-sm px-4 py-2 rounded-xl font-medium transition-all',
                tab === t ? 'bg-navy text-white' : 'text-slate-600 hover:bg-slate-100')}>
              {t}
              {t === 'Non lues' && unread > 0 && (
                <span className="ml-1 bg-red-500 text-white text-xs w-4 h-4 rounded-full inline-flex items-center justify-center">
                  {unread}
                </span>
              )}
            </button>
          ))}
        </div>
        {unread > 0 && (
          <button onClick={markAllRead} className="text-xs text-cyan hover:underline flex items-center gap-1">
            <CheckCheck size={14} /> Tout marquer comme lu
          </button>
        )}
      </div>

      {/* État vide */}
      {filtered.length === 0 && (
        <div className="text-center py-16">
          <Bell size={32} className="text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500">Aucune notification</p>
        </div>
      )}

      {/* Liste des notifications */}
      <div className="space-y-2">
        {filtered.map(n => (
          <div key={n.id}
            className={clsx('card p-4 flex items-start gap-3 transition-all hover:shadow-md cursor-pointer',
              !n.read && 'border-l-4 border-l-cyan')}
            onClick={() => markRead(n.id)}>
            <div className="mt-0.5 shrink-0">{NOTIF_ICONS[n.type]}</div>
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2">
                <p className={clsx('text-sm font-medium', !n.read ? 'text-slate-900' : 'text-slate-700')}>{n.title}</p>
                <span className="text-xs text-slate-400 shrink-0">{n.time}</span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">{n.desc}</p>
              <div className="flex items-center gap-2 mt-2">
                <span className={clsx('text-xs px-2 py-0.5 rounded-md font-medium', SOURCE_COLORS[n.source] || 'bg-slate-100 text-slate-600')}>
                  {n.source}
                </span>
                {!n.read && <span className="text-xs text-slate-400">· Cliquer pour marquer comme lu</span>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}