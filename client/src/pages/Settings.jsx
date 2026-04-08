// src/pages/Settings.jsx
import { useAuthStore } from '../store'
import { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ROLE_BADGES = {
  pm: { class: 'badge-pm', label: 'Project Manager' },
  consultant: { class: 'badge-consultant', label: 'Consultant' },
  rh_manager: { class: 'badge-rh', label: 'RH Responsable' },
}

const PREFERENCES = [
  ['Notifications email', 'Recevoir les alertes par email'],
  ['Notifications push', 'Alertes dans le navigateur'],
  ['Mode compact', 'Interface plus dense'],
]

function GoogleCalendarSection({ token }) {
  const [status, setStatus]   = useState(null)
  const [justLinked, setJustLinked] = useState(false)

  const fetchStatus = () => {
    if (!token) return
    fetch(`${API_BASE}/auth/google/status`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.json())
      .then(setStatus)
      .catch(() => setStatus({ connected: false }))
  }

  useEffect(() => {
    fetchStatus()
    // Si on revient de Google avec calendar_ok=true, signaler le succès
    const params = new URLSearchParams(window.location.search)
    if (params.get('calendar_ok') === 'true') {
      setJustLinked(true)
      // Nettoyer le paramètre de l'URL sans recharger la page
      window.history.replaceState({}, '', '/settings')
    }
  }, [token])

  const handleConnect = () => {
    window.location.href = `${API_BASE}/auth/google/connect?token=${token}`
  }

  const isConnected    = status?.connected && !status?.needs_reconnect
  const needsReconnect = status?.needs_reconnect

  return (
    <div className="card p-5">
      <h3 className="font-display font-bold text-navy mb-1">Google Calendar</h3>
      <p className="text-xs text-slate-400 mb-4">
        Connectez votre compte Google pour que l'assistant puisse gérer votre calendrier.
      </p>

      {justLinked && (
        <div className="mb-3 flex items-center gap-2 text-xs text-emerald-600 bg-emerald-50 border border-emerald-100 px-3 py-2 rounded-xl">
          <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
          Google Calendar connecté avec succès !
        </div>
      )}

      {status === null ? (
        <div className="text-sm text-slate-400">Chargement...</div>
      ) : isConnected ? (
        <div className="flex items-center gap-3 flex-wrap">
          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-600 bg-emerald-50 px-3 py-1.5 rounded-full">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
            Connecté
          </span>
          <span className="text-sm text-slate-500">{status.google_email}</span>
          <button
            onClick={handleConnect}
            className="ml-auto text-xs text-slate-400 hover:text-slate-600 underline"
          >
            Reconnecter
          </button>
        </div>
      ) : needsReconnect ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 border border-amber-100 px-3 py-2 rounded-xl">
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            </svg>
            L'accès a été révoqué. Veuillez reconnecter votre compte Google.
          </div>
          <button onClick={handleConnect} className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 text-white rounded-lg text-sm font-medium hover:bg-amber-600 transition-colors">
            Reconnecter Google Calendar
          </button>
        </div>
      ) : (
        <button
          onClick={handleConnect}
          className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Connecter Google Calendar
        </button>
      )}
    </div>
  )
}

export default function Settings() {
  const user = useAuthStore(s => s.user)
  const token = useAuthStore(s => s.token)
  const badge = ROLE_BADGES[user?.role] || ROLE_BADGES.consultant

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-5">
      {/* Profil */}
      <div className="card p-5">
        <h3 className="font-display font-bold text-navy mb-4">Profil</h3>
        <div className="flex items-center gap-4 mb-5">
          <div className="w-16 h-16 bg-navy rounded-2xl flex items-center justify-center">
            <span className="text-white text-xl font-bold">{user?.initials}</span>
          </div>
          <div>
            <div className="font-semibold text-slate-800 text-lg">{user?.name}</div>
            <div className="text-slate-500 text-sm">{user?.email}</div>
            <span className={badge.class}>{badge.label}</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-500 block mb-1">Prénom</label>
            <input className="input-field" defaultValue={user?.name?.split(' ')[0]} />
          </div>
          <div>
            <label className="text-xs text-slate-500 block mb-1">Nom</label>
            <input className="input-field" defaultValue={user?.name?.split(' ')[1]} />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-slate-500 block mb-1">Email</label>
            <input className="input-field" defaultValue={user?.email} />
          </div>
        </div>
        <button className="btn-primary mt-4 text-sm">Sauvegarder</button>
      </div>

      {/* Google Calendar */}
      <GoogleCalendarSection token={token} />

      {/* Préférences */}
      <div className="card p-5">
        <h3 className="font-display font-bold text-navy mb-4">Préférences</h3>
        {PREFERENCES.map(([label, desc]) => (
          <div key={label} className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0">
            <div>
              <div className="text-sm font-medium text-slate-700">{label}</div>
              <div className="text-xs text-slate-400">{desc}</div>
            </div>
            <label className="relative inline-flex cursor-pointer">
              <input type="checkbox" className="sr-only peer" defaultChecked />
              <div className="w-10 h-5 bg-slate-200 peer-checked:bg-navy rounded-full transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:w-4 after:h-4 after:bg-white after:rounded-full after:transition-transform peer-checked:after:translate-x-5" />
            </label>
          </div>
        ))}
      </div>
    </div>
  )
}