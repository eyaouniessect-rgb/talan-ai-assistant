// src/pages/rh/tabs/OrgTab.jsx
// Drill-down: Département → Team → Employé → Skills
import { useState, useEffect } from 'react'
import { ChevronRight, ArrowLeft, Building2, Users, User, Star } from 'lucide-react'
import { getDepartmentsApi, getTeamsApi, getEmployeesApi } from '../../../api/rh'
import clsx from 'clsx'

// ── Label helpers ───────────────────────────────────────

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
  principal: 'bg-amber-100 text-amber-700',
}

const SKILL_LEVEL_COLOR = {
  beginner:     'bg-slate-100 text-slate-500',
  intermediate: 'bg-sky-100 text-sky-600',
  advanced:     'bg-blue-100 text-blue-700',
  expert:       'bg-violet-100 text-violet-700',
}

// ── Components ──────────────────────────────────────────

function Breadcrumb({ items }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-5">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight size={12} className="text-slate-300" />}
          <span className={i === items.length - 1 ? 'text-navy font-medium' : ''}>{item}</span>
        </span>
      ))}
    </div>
  )
}

function Card({ onClick, children, className = '' }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left bg-white border border-slate-100 rounded-2xl p-5 shadow-sm',
        'hover:shadow-md hover:border-cyan/30 transition-all duration-200 group',
        className,
      )}
    >
      {children}
    </button>
  )
}

// ── View: Departments ───────────────────────────────────

function DepartmentList({ departments, onSelect }) {
  return (
    <div>
      <Breadcrumb items={['Départements']} />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {departments.map(d => (
          <Card key={d.id} onClick={() => onSelect(d)}>
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 bg-navy/5 rounded-xl flex items-center justify-center shrink-0 group-hover:bg-cyan/10 transition-colors">
                <Building2 size={18} className="text-navy/60 group-hover:text-cyan transition-colors" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-800 text-sm truncate">
                  {DEPT_LABELS[d.name] || d.name}
                </div>
                <div className="text-xs text-slate-400 mt-0.5">{d.team_count} équipe{d.team_count !== 1 ? 's' : ''}</div>
              </div>
              <ChevronRight size={15} className="text-slate-300 group-hover:text-cyan transition-colors mt-0.5 shrink-0" />
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}

// ── View: Teams of a department ─────────────────────────

function TeamList({ department, teams, onSelect, onBack }) {
  const deptTeams = teams.filter(t => t.department === department.name)
  return (
    <div>
      <Breadcrumb items={['Départements', DEPT_LABELS[department.name] || department.name, 'Équipes']} />
      <button onClick={onBack} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-navy mb-5 transition-colors">
        <ArrowLeft size={13} /> Retour
      </button>
      {deptTeams.length === 0 ? (
        <p className="text-sm text-slate-400">Aucune équipe dans ce département.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {deptTeams.map(t => (
            <Card key={t.id} onClick={() => onSelect(t)}>
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 bg-cyan/5 rounded-xl flex items-center justify-center shrink-0 group-hover:bg-cyan/10 transition-colors">
                  <Users size={18} className="text-cyan/70 group-hover:text-cyan transition-colors" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-800 text-sm">{t.name}</div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    Manager : {t.manager_name || '—'}
                  </div>
                </div>
                <ChevronRight size={15} className="text-slate-300 group-hover:text-cyan transition-colors mt-0.5 shrink-0" />
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ── View: Employees of a team ───────────────────────────

function EmployeeList({ team, employees, onSelect, onBack }) {
  const teamEmps = employees.filter(e => e.team === team.name)
  return (
    <div>
      <Breadcrumb items={['Départements', team.department ? (DEPT_LABELS[team.department] || team.department) : '…', team.name, 'Employés']} />
      <button onClick={onBack} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-navy mb-5 transition-colors">
        <ArrowLeft size={13} /> Retour
      </button>

      {/* Manager card */}
      {team.manager_name && (
        <div className="mb-4 p-4 bg-amber-50 border border-amber-100 rounded-2xl flex items-center gap-3">
          <div className="w-9 h-9 bg-amber-200 rounded-xl flex items-center justify-center shrink-0">
            <Star size={15} className="text-amber-700" />
          </div>
          <div>
            <div className="text-xs text-amber-600 font-medium uppercase tracking-wide">Manager</div>
            <div className="text-sm font-semibold text-slate-800">{team.manager_name}</div>
          </div>
        </div>
      )}

      {teamEmps.length === 0 ? (
        <p className="text-sm text-slate-400">Aucun employé dans cette équipe.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {teamEmps.map(e => (
            <Card key={e.id} onClick={() => onSelect(e)}>
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 bg-slate-100 rounded-xl flex items-center justify-center shrink-0 group-hover:bg-cyan/10 transition-colors">
                  <User size={16} className="text-slate-500 group-hover:text-cyan transition-colors" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-800 text-sm truncate">{e.name}</div>
                  <div className="text-xs text-slate-400 mt-0.5 truncate">{e.job_title || e.role}</div>
                  <div className="flex items-center gap-2 mt-1.5">
                    {e.seniority && (
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SENIORITY_COLOR[e.seniority] || 'bg-slate-100 text-slate-500'}`}>
                        {e.seniority}
                      </span>
                    )}
                    <span className="text-xs text-slate-300">{e.skills?.length || 0} skill{e.skills?.length !== 1 ? 's' : ''}</span>
                  </div>
                </div>
                <ChevronRight size={15} className="text-slate-300 group-hover:text-cyan transition-colors mt-0.5 shrink-0" />
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ── View: Employee skills ───────────────────────────────

function EmployeeDetail({ employee, onBack }) {
  return (
    <div>
      <Breadcrumb items={['Départements', employee.department ? (DEPT_LABELS[employee.department] || employee.department) : '…', employee.team || '…', employee.name]} />
      <button onClick={onBack} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-navy mb-5 transition-colors">
        <ArrowLeft size={13} /> Retour
      </button>

      <div className="bg-white border border-slate-100 rounded-2xl p-6 shadow-sm max-w-lg">
        {/* Header */}
        <div className="flex items-center gap-4 mb-5">
          <div className="w-14 h-14 bg-navy rounded-2xl flex items-center justify-center shrink-0">
            <span className="text-white text-lg font-bold">
              {employee.name?.split(' ').map(n => n[0]).join('').slice(0, 2)}
            </span>
          </div>
          <div>
            <div className="font-bold text-navy text-base">{employee.name}</div>
            <div className="text-sm text-slate-500">{employee.job_title || '—'}</div>
            <div className="flex items-center gap-2 mt-1">
              {employee.seniority && (
                <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${SENIORITY_COLOR[employee.seniority] || ''}`}>
                  {employee.seniority}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Info grid */}
        <div className="grid grid-cols-2 gap-3 mb-5">
          {[
            { label: 'Email', value: employee.email },
            { label: 'Équipe', value: employee.team || '—' },
            { label: 'Département', value: employee.department ? (DEPT_LABELS[employee.department] || employee.department) : '—' },
            { label: 'Manager', value: employee.manager || '—' },
            { label: "Solde congés", value: `${employee.leave_balance} j` },
            { label: "Embauché le", value: employee.hire_date ? new Date(employee.hire_date).toLocaleDateString('fr-FR') : '—' },
          ].map(({ label, value }) => (
            <div key={label} className="bg-slate-50 rounded-xl p-3">
              <div className="text-xs text-slate-400 mb-0.5">{label}</div>
              <div className="text-sm font-medium text-slate-700 truncate">{value}</div>
            </div>
          ))}
        </div>

        {/* Skills */}
        <div>
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Compétences</div>
          {employee.skills?.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {employee.skills.map(s => (
                <span key={s.name}
                  className={`text-xs px-3 py-1.5 rounded-full font-medium flex items-center gap-1.5 ${SKILL_LEVEL_COLOR[s.level] || 'bg-slate-100 text-slate-600'}`}>
                  {s.name}
                  <span className="opacity-60 text-[10px]">{s.level}</span>
                </span>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">Aucune compétence renseignée.</p>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main OrgTab ─────────────────────────────────────────

export default function OrgTab() {
  const [departments, setDepartments] = useState([])
  const [teams, setTeams]             = useState([])
  const [employees, setEmployees]     = useState([])
  const [loading, setLoading]         = useState(true)

  // Drill-down state
  const [selectedDept, setSelectedDept]   = useState(null)
  const [selectedTeam, setSelectedTeam]   = useState(null)
  const [selectedEmp,  setSelectedEmp]    = useState(null)

  useEffect(() => {
    Promise.all([getDepartmentsApi(), getTeamsApi(), getEmployeesApi()])
      .then(([d, t, e]) => { setDepartments(d); setTeams(t); setEmployees(e) })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="p-10 text-center text-sm text-slate-400">Chargement…</div>
  }

  if (selectedEmp) {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <EmployeeDetail
          employee={selectedEmp}
          onBack={() => setSelectedEmp(null)}
        />
      </div>
    )
  }

  if (selectedTeam) {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <EmployeeList
          team={selectedTeam}
          employees={employees}
          onSelect={setSelectedEmp}
          onBack={() => setSelectedTeam(null)}
        />
      </div>
    )
  }

  if (selectedDept) {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <TeamList
          department={selectedDept}
          teams={teams}
          onSelect={setSelectedTeam}
          onBack={() => { setSelectedDept(null); setSelectedTeam(null) }}
        />
      </div>
    )
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <DepartmentList departments={departments} onSelect={setSelectedDept} />
    </div>
  )
}
