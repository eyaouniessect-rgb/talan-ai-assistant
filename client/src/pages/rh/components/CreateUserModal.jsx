// src/pages/rh/components/CreateUserModal.jsx
import { useState, useEffect } from 'react'
import { X, UserPlus, Loader, ChevronRight } from 'lucide-react'
import { createUserApi, getDepartmentsApi, getTeamsApi, getSkillsApi } from '../../../api/rh'
import SkillsPicker from './SkillsPicker'

const ROLES = [
  { value: 'consultant', label: 'Consultant' },
  { value: 'pm',         label: 'Project Manager' },
  { value: 'rh',         label: 'RH' },
]

const SENIORITIES = [
  { value: 'junior',    label: 'Junior' },
  { value: 'mid',       label: 'Mid' },
  { value: 'senior',    label: 'Senior' },
  { value: 'lead',      label: 'Lead' },
  { value: 'principal', label: 'Principal' },
]

const DEPT_LABELS = {
  innovation_factory: 'Innovation Factory',
  salesforce:         'Salesforce',
  data:               'Data & Analytics',
  digital_factory:    'Digital Factory',
  testing:            'Testing',
  cloud:              'Cloud',
  service_now:        'ServiceNow',
}

const today = new Date().toISOString().split('T')[0]

export default function CreateUserModal({ onClose, onCreated }) {
  const [step, setStep]       = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const [success, setSuccess] = useState(false)

  // Référentiels chargés depuis l'API
  const [departments, setDepartments]     = useState([])
  const [allTeams, setAllTeams]           = useState([])
  const [existingSkills, setExistingSkills] = useState([])

  // Formulaire
  const [form, setForm] = useState({
    name: '', email: '', role: 'consultant',
    department_id: '', team_id: '',
    job_title: '', seniority: '', hire_date: today,
    skills: [],   // [{ name, level }]
  })

  useEffect(() => {
    Promise.all([getDepartmentsApi(), getTeamsApi(), getSkillsApi()])
      .then(([d, t, s]) => {
        setDepartments(d)
        setAllTeams(t)
        setExistingSkills(s)
      })
  }, [])

  const set = (k, v) => {
    setForm(prev => {
      const next = { ...prev, [k]: v }
      if (k === 'department_id') next.team_id = ''
      return next
    })
  }

  const filteredTeams = allTeams.filter(t => {
    if (!form.department_id) return false
    const dept = departments.find(d => d.id === Number(form.department_id))
    return dept && t.department === dept.name
  })

  const canGoStep2 = form.name.trim() && form.email.trim() && form.role
  const canSubmit  = !!form.team_id

  const submit = async () => {
    setError(null)
    setLoading(true)
    try {
      const payload = {
        name:      form.name,
        email:     form.email,
        role:      form.role,
        team_id:   Number(form.team_id),
        job_title: form.job_title  || null,
        seniority: form.seniority  || null,
        hire_date: form.hire_date  || null,
        skills:    form.skills,
      }
      const user = await createUserApi(payload)
      setSuccess(true)
      onCreated(user)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Erreur lors de la création')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <UserPlus size={18} className="text-cyan" />
            <h2 className="text-sm font-semibold text-navy">
              Créer un compte
              {!success && <span className="ml-2 text-slate-400 font-normal">— Étape {step}/2</span>}
            </h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 p-1 rounded-lg hover:bg-slate-100 transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Barre de progression */}
        {!success && (
          <div className="flex gap-1 px-6 pt-4">
            {[1, 2].map(s => (
              <div key={s} className={`h-1 flex-1 rounded-full transition-colors ${s <= step ? 'bg-cyan' : 'bg-slate-100'}`} />
            ))}
          </div>
        )}

        {/* ── Succès ─────────────────────────────────────── */}
        {success ? (
          <div className="px-6 py-8 text-center space-y-3">
            <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mx-auto">
              <span className="text-green-600 text-xl">✓</span>
            </div>
            <p className="text-sm font-medium text-slate-700">Compte et profil employé créés</p>
            <p className="text-xs text-slate-400">Les identifiants ont été envoyés par email.</p>
            <button onClick={onClose} className="mt-2 px-5 py-2 bg-navy text-white text-sm rounded-xl hover:bg-navy/90 transition-colors">
              Fermer
            </button>
          </div>

        /* ── Étape 1 : Compte ──────────────────────────── */
        ) : step === 1 ? (
          <div className="px-6 py-5 space-y-4">
            <p className="text-xs text-slate-400 font-medium uppercase tracking-wide">Informations du compte</p>

            <Field label="Nom complet">
              <input type="text" required value={form.name}
                onChange={e => set('name', e.target.value)}
                placeholder="Prénom Nom" className={inputCls} />
            </Field>

            <Field label="Email">
              <input type="email" required value={form.email}
                onChange={e => set('email', e.target.value)}
                placeholder="prenom.nom@talan.tn" className={inputCls} />
            </Field>

            <Field label="Rôle">
              <select value={form.role} onChange={e => set('role', e.target.value)} className={inputCls}>
                {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </Field>

            <div className="flex gap-3 pt-1">
              <button type="button" onClick={onClose}
                className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm text-slate-600 hover:bg-slate-50 transition-colors">
                Annuler
              </button>
              <button type="button" disabled={!canGoStep2} onClick={() => setStep(2)}
                className="flex-1 py-2.5 bg-navy text-white rounded-xl text-sm font-medium hover:bg-navy/90 transition-colors flex items-center justify-center gap-2 disabled:opacity-40">
                Suivant <ChevronRight size={14} />
              </button>
            </div>
          </div>

        /* ── Étape 2 : Profil employé ──────────────────── */
        ) : (
          <div className="px-6 py-5 space-y-4 max-h-[70vh] overflow-y-auto">
            <p className="text-xs text-slate-400 font-medium uppercase tracking-wide">Profil employé</p>

            {/* Département → Équipe en cascade */}
            <Field label="Département *">
              <select value={form.department_id} onChange={e => set('department_id', e.target.value)} className={inputCls}>
                <option value="">Choisir un département…</option>
                {departments.map(d => (
                  <option key={d.id} value={d.id}>{DEPT_LABELS[d.name] || d.name}</option>
                ))}
              </select>
            </Field>

            <Field label="Équipe *">
              <select value={form.team_id} onChange={e => set('team_id', e.target.value)}
                disabled={!form.department_id}
                className={`${inputCls} disabled:opacity-50 disabled:cursor-not-allowed`}>
                <option value="">
                  {form.department_id ? 'Choisir une équipe…' : '— Sélectionner un département d\'abord —'}
                </option>
                {filteredTeams.map(t => (
                  <option key={t.id} value={t.id}>
                    {t.name}{t.manager_name ? ` · Manager : ${t.manager_name}` : ''}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Intitulé de poste">
              <input type="text" value={form.job_title}
                onChange={e => set('job_title', e.target.value)}
                placeholder="ex: Développeur Full Stack" className={inputCls} />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Séniorité">
                <select value={form.seniority} onChange={e => set('seniority', e.target.value)} className={inputCls}>
                  <option value="">— Optionnel —</option>
                  {SENIORITIES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </Field>
              <Field label="Date d'embauche">
                <input type="date" value={form.hire_date}
                  onChange={e => set('hire_date', e.target.value)} className={inputCls} />
              </Field>
            </div>

            {/* SkillsPicker — remplace l'ancienne logique */}
            <Field label="Compétences">
              <SkillsPicker
                existingSkills={existingSkills}
                value={form.skills}
                onChange={skills => set('skills', skills)}
              />
            </Field>

            {error && (
              <p className="text-xs text-red-500 bg-red-50 border border-red-100 rounded-xl px-3 py-2">{error}</p>
            )}

            <div className="flex gap-3 pt-1">
              <button type="button" onClick={() => { setStep(1); setError(null) }}
                className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm text-slate-600 hover:bg-slate-50 transition-colors">
                Retour
              </button>
              <button type="button" onClick={submit} disabled={loading || !canSubmit}
                className="flex-1 py-2.5 bg-navy text-white rounded-xl text-sm font-medium hover:bg-navy/90 transition-colors flex items-center justify-center gap-2 disabled:opacity-40">
                {loading && <Loader size={14} className="animate-spin" />}
                Créer le compte
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const inputCls = 'w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white'

function Field({ label, children }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-slate-500">{label}</label>
      {children}
    </div>
  )
}
