// src/pages/Settings.jsx
import { useAuthStore } from '../store'
import clsx from 'clsx'

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

export default function Settings() {
  const user = useAuthStore(s => s.user)
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