// src/pages/rh/components/EditEmployeeModal.jsx
import { useState, useEffect } from 'react'
import { X, Save, Loader } from 'lucide-react'
import { updateEmployeeApi, getTeamsApi, getEmployeesApi } from '../../../api/rh'

const SENIORITIES = [
  { value: 'junior',    label: 'Junior' },
  { value: 'mid',       label: 'Mid' },
  { value: 'senior',    label: 'Senior' },
  { value: 'lead',      label: 'Lead' },
  { value: 'principal', label: 'Principal' },
]

export default function EditEmployeeModal({ employee, onClose, onSaved }) {
  const [form, setForm] = useState({
    job_title:  employee.job_title  || '',
    seniority:  employee.seniority  || '',
    team_id:    '',
    manager_id: '',
  })
  const [teams, setTeams]         = useState([])
  const [managers, setManagers]   = useState([])
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')
  const [success, setSuccess]     = useState(false)

  useEffect(() => {
    Promise.all([getTeamsApi(), getEmployeesApi()]).then(([t, emps]) => {
      setTeams(t)
      setManagers(emps.filter(e => e.id !== employee.id))
    })
  }, [employee.id])

  const set = (field, value) => setForm(f => ({ ...f, [field]: value }))

  const handleSave = async () => {
    setLoading(true)
    setError('')
    try {
      const payload = {}
      if (form.job_title)  payload.job_title  = form.job_title
      if (form.seniority)  payload.seniority  = form.seniority
      if (form.team_id)    payload.team_id    = parseInt(form.team_id)
      if (form.manager_id) payload.manager_id = parseInt(form.manager_id)

      await updateEmployeeApi(employee.id, payload)
      setSuccess(true)
      setTimeout(() => { onSaved(); onClose() }, 1000)
    } catch (e) {
      setError(e.response?.data?.detail || 'Erreur lors de la mise à jour')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <div className="font-bold text-navy text-sm">Modifier l'employé</div>
            <div className="text-xs text-slate-400 mt-0.5">{employee.name}</div>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors">
            <X size={16} className="text-slate-400" />
          </button>
        </div>

        {/* Form */}
        <div className="px-6 py-5 space-y-4">
          {/* Poste */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">Intitulé du poste</label>
            <input
              type="text"
              value={form.job_title}
              onChange={e => set('job_title', e.target.value)}
              placeholder={employee.job_title || 'Ex : Développeur Fullstack'}
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan"
            />
          </div>

          {/* Séniorité */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">Séniorité</label>
            <select
              value={form.seniority}
              onChange={e => set('seniority', e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan bg-white"
            >
              <option value="">— Choisir —</option>
              {SENIORITIES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          {/* Équipe */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">
              Équipe <span className="text-slate-300 font-normal">(actuelle : {employee.team || '—'})</span>
            </label>
            <select
              value={form.team_id}
              onChange={e => set('team_id', e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan bg-white"
            >
              <option value="">— Garder l'équipe actuelle —</option>
              {teams.map(t => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>

          {/* Manager */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">
              Manager <span className="text-slate-300 font-normal">(actuel : {employee.manager || '—'})</span>
            </label>
            <select
              value={form.manager_id}
              onChange={e => set('manager_id', e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan bg-white"
            >
              <option value="">— Garder le manager actuel —</option>
              {managers.map(m => (
                <option key={m.id} value={m.id}>{m.name} — {m.job_title || m.role}</option>
              ))}
            </select>
          </div>

          {error && (
            <div className="text-xs text-red-500 bg-red-50 border border-red-100 rounded-xl px-3 py-2">
              {error}
            </div>
          )}
          {success && (
            <div className="text-xs text-green-600 bg-green-50 border border-green-100 rounded-xl px-3 py-2">
              ✅ Informations mises à jour avec succès !
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-500 hover:bg-slate-50 rounded-xl transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={handleSave}
            disabled={loading || success}
            className="px-4 py-2 text-sm bg-navy text-white rounded-xl hover:bg-navy/90 transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {loading ? <Loader size={13} className="animate-spin" /> : <Save size={13} />}
            Enregistrer
          </button>
        </div>
      </div>
    </div>
  )
}
