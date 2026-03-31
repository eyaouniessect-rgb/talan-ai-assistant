// src/pages/rh/tabs/UsersTab.jsx
import { useState, useEffect } from 'react'
import { UserPlus, Search, RefreshCw } from 'lucide-react'
import { getUsersApi } from '../../../api/rh'
import CreateUserModal from '../components/CreateUserModal'

const ROLE_BADGE = {
  consultant: 'bg-blue-100 text-blue-700',
  pm:         'bg-purple-100 text-purple-700',
  rh:         'bg-emerald-100 text-emerald-700',
}

const ROLE_LABEL = {
  consultant: 'Consultant',
  pm:         'Project Manager',
  rh:         'RH',
}

export default function UsersTab() {
  const [users, setUsers]         = useState([])
  const [loading, setLoading]     = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [search, setSearch]       = useState('')

  const load = async () => {
    setLoading(true)
    try {
      setUsers(await getUsersApi())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const filtered = users.filter(u =>
    u.name.toLowerCase().includes(search.toLowerCase()) ||
    u.email.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="p-6 space-y-5 max-w-5xl mx-auto">
      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Rechercher un utilisateur…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none"
          />
        </div>
        <button onClick={load} className="p-2.5 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors text-slate-500">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>
        <button onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-navy text-white rounded-xl text-sm font-medium hover:bg-navy/90 transition-colors">
          <UserPlus size={15} />
          Nouveau compte
        </button>
      </div>

      {/* Table */}
      <div className="bg-white border border-slate-100 rounded-2xl overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr>
              {['Nom', 'Email', 'Rôle', 'Statut', 'Créé le'].map(h => (
                <th key={h} className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {loading ? (
              <tr><td colSpan={5} className="text-center py-10 text-slate-400 text-sm">Chargement…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={5} className="text-center py-10 text-slate-400 text-sm">Aucun résultat</td></tr>
            ) : filtered.map(u => (
              <tr key={u.id} className="hover:bg-slate-50/60 transition-colors">
                <td className="px-5 py-3.5 font-medium text-slate-800">{u.name}</td>
                <td className="px-5 py-3.5 text-slate-500">{u.email}</td>
                <td className="px-5 py-3.5">
                  <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${ROLE_BADGE[u.role] || 'bg-slate-100 text-slate-600'}`}>
                    {ROLE_LABEL[u.role] || u.role}
                  </span>
                </td>
                <td className="px-5 py-3.5">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${u.is_active ? 'text-green-600 bg-green-50' : 'text-red-500 bg-red-50'}`}>
                    {u.is_active ? 'Actif' : 'Inactif'}
                  </span>
                </td>
                <td className="px-5 py-3.5 text-slate-400 text-xs">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString('fr-FR') : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && (
        <CreateUserModal
          onClose={() => setShowModal(false)}
          onCreated={user => { setUsers(prev => [user, ...prev]); setShowModal(false) }}
        />
      )}
    </div>
  )
}
