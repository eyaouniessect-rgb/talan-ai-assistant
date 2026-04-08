// src/pages/rh/tabs/UsersTab.jsx
import { useState, useEffect, useMemo } from 'react'
import { UserPlus, Search, RefreshCw, ChevronLeft, ChevronRight, Mail, PowerOff, Power } from 'lucide-react'
import { getEmployeesApi, getDepartmentsApi, getTeamsApi, toggleUserActiveApi } from '../../../api/rh'
import CreateUserModal from '../components/CreateUserModal'
import ContactModal from '../components/ContactModal'
import clsx from 'clsx'

const PAGE_SIZE = 10

const DEPT_LABELS = {
  innovation_factory: 'Innovation Factory',
  salesforce:         'Salesforce',
  data:               'Data & Analytics',
  digital_factory:    'Digital Factory',
  testing:            'Testing',
  cloud:              'Cloud',
  service_now:        'ServiceNow',
}

const SENIORITY_COLOR = {
  junior:    'bg-slate-100 text-slate-600',
  mid:       'bg-blue-100 text-blue-700',
  senior:    'bg-indigo-100 text-indigo-700',
  lead:      'bg-violet-100 text-violet-700',
  head:      'bg-amber-100 text-amber-700',
  principal: 'bg-rose-100 text-rose-700',
}

export default function UsersTab() {
  const [employees, setEmployees]   = useState([])
  const [departments, setDepartments] = useState([])
  const [teams, setTeams]           = useState([])
  const [loading, setLoading]       = useState(true)
  const [showModal, setShowModal]   = useState(false)
  const [contactEmp, setContactEmp] = useState(null)

  // Filters
  const [search, setSearch]         = useState('')
  const [filterDept, setFilterDept] = useState('')
  const [filterTeam, setFilterTeam] = useState('')
  const [filterSeniority, setFilterSeniority] = useState('')

  // Pagination
  const [page, setPage] = useState(1)

  const load = async () => {
    setLoading(true)
    try {
      const [emps, depts, tms] = await Promise.all([
        getEmployeesApi(),
        getDepartmentsApi(),
        getTeamsApi(),
      ])
      setEmployees(emps)
      setDepartments(depts)
      setTeams(tms)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  // Reset page when filters change
  useEffect(() => { setPage(1) }, [search, filterDept, filterTeam, filterSeniority])

  // Teams filtered by selected dept
  const teamsForDept = useMemo(() => {
    if (!filterDept) return teams
    return teams.filter(t => t.department === filterDept)
  }, [teams, filterDept])

  // Client-side filtering
  const filtered = useMemo(() => {
    return employees.filter(e => {
      const q = search.toLowerCase()
      const matchSearch = !q ||
        e.name.toLowerCase().includes(q) ||
        e.email.toLowerCase().includes(q) ||
        (e.job_title || '').toLowerCase().includes(q)
      const matchDept = !filterDept || e.department === filterDept
      const matchTeam = !filterTeam || e.team === filterTeam
      const matchSeniority = !filterSeniority || e.seniority === filterSeniority
      return matchSearch && matchDept && matchTeam && matchSeniority
    })
  }, [employees, search, filterDept, filterTeam, filterSeniority])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paginated  = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleToggleActive = async (emp) => {
    try {
      const res = await toggleUserActiveApi(emp.user_id)
      setEmployees(prev => prev.map(e =>
        e.user_id === emp.user_id ? { ...e, is_active: res.is_active } : e
      ))
    } catch (err) {
      console.error('Erreur toggle active:', err)
    }
  }

  return (
    <div className="p-6 space-y-5 max-w-6xl mx-auto">

      {/* ── Toolbar ── */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Rechercher…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none"
          />
        </div>

        {/* Filtre département */}
        <select
          value={filterDept}
          onChange={e => { setFilterDept(e.target.value); setFilterTeam('') }}
          className="border border-slate-200 rounded-xl px-3 py-2.5 text-sm text-slate-600 focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none bg-white"
        >
          <option value="">Tous les départements</option>
          {departments.map(d => (
            <option key={d.id} value={d.name}>{DEPT_LABELS[d.name] || d.name}</option>
          ))}
        </select>

        {/* Filtre team */}
        <select
          value={filterTeam}
          onChange={e => setFilterTeam(e.target.value)}
          className="border border-slate-200 rounded-xl px-3 py-2.5 text-sm text-slate-600 focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none bg-white"
        >
          <option value="">Toutes les équipes</option>
          {teamsForDept.map(t => (
            <option key={t.id} value={t.name}>{t.name}</option>
          ))}
        </select>

        {/* Filtre seniority */}
        <select
          value={filterSeniority}
          onChange={e => setFilterSeniority(e.target.value)}
          className="border border-slate-200 rounded-xl px-3 py-2.5 text-sm text-slate-600 focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none bg-white"
        >
          <option value="">Tous les niveaux</option>
          <option value="junior">Junior</option>
          <option value="mid">Mid</option>
          <option value="senior">Senior</option>
          <option value="lead">Tech Lead</option>
          <option value="head">Head</option>
          <option value="principal">Principal / DG</option>
        </select>

        <button onClick={load} className="p-2.5 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors text-slate-500 shrink-0">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-navy text-white rounded-xl text-sm font-medium hover:bg-navy/90 transition-colors shrink-0"
        >
          <UserPlus size={15} /> Nouveau compte
        </button>
      </div>

      {/* ── Table ── */}
      <div className="bg-white border border-slate-100 rounded-2xl overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr>
              {['Nom', 'Email', 'Job Title', 'Seniority', 'Équipe', 'Statut', 'Actions'].map(h => (
                <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {loading ? (
              <tr><td colSpan={7} className="text-center py-10 text-slate-400 text-sm">Chargement…</td></tr>
            ) : paginated.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-10 text-slate-400 text-sm">Aucun résultat</td></tr>
            ) : paginated.map(e => (
              <tr key={e.id} className={clsx('hover:bg-slate-50/60 transition-colors', !e.is_active && 'opacity-50')}>
                {/* Nom */}
                <td className="px-4 py-3 font-medium text-slate-800 whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 bg-navy/10 rounded-lg flex items-center justify-center text-xs font-bold text-navy shrink-0">
                      {e.name?.split(' ').map(n => n[0]).join('').slice(0, 2)}
                    </div>
                    {e.name}
                  </div>
                </td>
                {/* Email */}
                <td className="px-4 py-3 text-slate-500 text-xs">{e.email}</td>
                {/* Job Title */}
                <td className="px-4 py-3 text-slate-600 text-xs">{e.job_title || '—'}</td>
                {/* Seniority */}
                <td className="px-4 py-3">
                  {e.seniority ? (
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SENIORITY_COLOR[e.seniority] || 'bg-slate-100 text-slate-600'}`}>
                      {e.seniority}
                    </span>
                  ) : '—'}
                </td>
                {/* Équipe */}
                <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">{e.team || '—'}</td>
                {/* Statut */}
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${e.is_active ? 'text-green-600 bg-green-50' : 'text-red-500 bg-red-50'}`}>
                    {e.is_active ? 'Actif' : 'Inactif'}
                  </span>
                </td>
                {/* Actions */}
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    {/* Contacter */}
                    <button
                      onClick={() => setContactEmp(e)}
                      title="Contacter"
                      className="p-1.5 rounded-lg hover:bg-cyan/10 text-cyan transition-colors"
                    >
                      <Mail size={14} />
                    </button>
                    {/* Désactiver / Activer */}
                    <button
                      onClick={() => handleToggleActive(e)}
                      title={e.is_active ? 'Désactiver' : 'Activer'}
                      className={clsx(
                        'p-1.5 rounded-lg transition-colors',
                        e.is_active
                          ? 'hover:bg-red-50 text-slate-400 hover:text-red-500'
                          : 'hover:bg-green-50 text-slate-400 hover:text-green-500'
                      )}
                    >
                      {e.is_active ? <PowerOff size={14} /> : <Power size={14} />}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>{filtered.length} employé{filtered.length !== 1 ? 's' : ''} · page {page}/{totalPages}</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={15} />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
              <button
                key={p}
                onClick={() => setPage(p)}
                className={clsx(
                  'w-8 h-8 rounded-lg text-xs font-medium transition-colors',
                  p === page ? 'bg-navy text-white' : 'hover:bg-slate-100 text-slate-600'
                )}
              >
                {p}
              </button>
            ))}
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight size={15} />
            </button>
          </div>
        </div>
      )}
      {filtered.length > 0 && totalPages === 1 && (
        <p className="text-xs text-slate-400">{filtered.length} employé{filtered.length !== 1 ? 's' : ''}</p>
      )}

      {/* ── Modals ── */}
      {showModal && (
        <CreateUserModal
          onClose={() => setShowModal(false)}
          onCreated={() => { load(); setShowModal(false) }}
        />
      )}
      {contactEmp && (
        <ContactModal
          employee={contactEmp}
          onClose={() => setContactEmp(null)}
        />
      )}
    </div>
  )
}
