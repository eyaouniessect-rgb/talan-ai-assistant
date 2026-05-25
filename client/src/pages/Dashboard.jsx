import { useState, useEffect } from 'react'
import { useAuthStore } from '../store'
import { PROJECTS, TICKETS, TEAM_MEMBERS, ACTIVITY } from '../data/mock'
import { TrendingUp, Clock, AlertCircle, MessageSquare, CheckCircle, Circle, ArrowRight, Users, X, Star, Calendar, MapPin, Video, UserCheck, ListTodo, Loader2, Flame, FolderKanban } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RTooltip } from 'recharts'
import { useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import { getPMDashboard, getPMEvents, getPMDelivery, getConsultantDashboard } from '../api/pm'
import DeliverySection from './pm/components/DeliverySection'

const STATUS_COLORS = {
  'En cours': 'bg-blue-50 text-blue-700',
  'Terminé': 'bg-green-50 text-green-700',
  'En attente': 'bg-amber-50 text-amber-700',
}
const PRIORITY_COLORS = {
  'High': 'bg-red-50 text-red-700',
  'Medium': 'bg-amber-50 text-amber-700',
  'Low': 'bg-green-50 text-green-700',
}

function MetricCard({ icon:Icon, label, value, color, sub }) {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between mb-3">
        <div className={clsx('w-10 h-10 rounded-xl flex items-center justify-center', color)}>
          <Icon size={19}/>
        </div>
      </div>
      <div className="text-2xl font-display font-bold text-navy mb-0.5">{value}</div>
      <div className="text-sm text-slate-500">{label}</div>
      {sub && <div className="text-xs text-slate-400 mt-1">{sub}</div>}
    </div>
  )
}

function ProgressBar({ value }) {
  return (
    <div className="w-full bg-slate-100 rounded-full h-1.5 mt-2">
      <div className="bg-cyan h-1.5 rounded-full transition-all"
        style={{ width:`${value}%` }}/>
    </div>
  )
}

// Formate une date ISO en "14 mai" ou "14 mai 2026" (si année différente)
function _fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const months = ['jan','fév','mar','avr','mai','jun','jul','aoû','sep','oct','nov','déc']
  const thisYear = new Date().getFullYear()
  const suffix = d.getFullYear() !== thisYear ? ` ${d.getFullYear()}` : ''
  return `${d.getDate()} ${months[d.getMonth()]}${suffix}`
}

// Carte projet pour le consultant : nom + client + sprint actif + compteurs tickets + allocation SP
function ConsultantProjectCard({ project }) {
  const t   = project.tickets    || { to_do: 0, in_progress: 0, done: 0, total: 0 }
  const sp  = project.allocation || { allocated_sp: 0, capacity_sp: 8, allocation_pct: 0, seniority: 'MID' }
  const spr = project.sprint     || { start_date: null, end_date: null, days_remaining: null, is_overdue: false }

  const progressPct  = t.total > 0 ? Math.round((t.done / t.total) * 100) : 0
  const allocationPct = Math.min(sp.allocation_pct, 100)

  const daysLabel = spr.days_remaining === null ? null
    : spr.is_overdue
      ? `+${Math.abs(spr.days_remaining)}j débordement`
      : spr.days_remaining === 0 ? 'Dernier jour'
      : `${spr.days_remaining}j restants`

  const daysColor = !daysLabel ? ''
    : spr.is_overdue              ? 'bg-red-50 text-red-600'
    : spr.days_remaining <= 2     ? 'bg-amber-50 text-amber-600'
    : 'bg-green-50 text-green-700'

  return (
    <div className="p-4 bg-slate-50 rounded-xl space-y-3">
      {/* ── En-tête : nom + badge sprint ── */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-800 truncate">{project.name}</div>
          <div className="text-xs text-slate-400 truncate">{project.client_name}</div>
        </div>
        {project.current_sprint_number && (
          <span className="text-[11px] bg-cyan-50 text-cyan-700 px-2 py-0.5 rounded-full font-medium shrink-0">
            Sprint {project.current_sprint_number}
          </span>
        )}
      </div>

      {/* ── Dates sprint + chip jours restants ── */}
      {(spr.start_date || spr.end_date) && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-1">
            <Calendar size={11} className="shrink-0"/>
            <span>{_fmtDate(spr.start_date)}</span>
            <span className="text-slate-300">→</span>
            <span>{_fmtDate(spr.end_date)}</span>
          </div>
          {daysLabel && (
            <span className={clsx('px-2 py-0.5 rounded-full text-[11px] font-medium', daysColor)}>
              {daysLabel}
            </span>
          )}
        </div>
      )}

      {/* ── Allocation SP ── */}
      <div>
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-slate-500">Allocation sprint</span>
          <span className="font-semibold text-slate-700">
            {sp.allocated_sp}/{sp.capacity_sp} SP
            <span className="text-slate-400 font-normal ml-1">({allocationPct}%)</span>
          </span>
        </div>
        <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
          <div
            className={clsx('h-1.5 rounded-full transition-all',
              allocationPct >= 90 ? 'bg-red-400' : allocationPct >= 70 ? 'bg-amber-400' : 'bg-cyan')}
            style={{ width: `${allocationPct}%` }}
          />
        </div>
      </div>

      {/* ── Compteurs tickets ── */}
      <div className="flex items-center gap-3 text-xs">
        <div className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-400"/>
          <span className="text-slate-500">À faire</span>
          <span className="font-semibold text-slate-700">{t.to_do}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-500"/>
          <span className="text-slate-500">En cours</span>
          <span className="font-semibold text-slate-700">{t.in_progress}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500"/>
          <span className="text-slate-500">Terminés</span>
          <span className="font-semibold text-slate-700">{t.done}</span>
        </div>
        <div className="ml-auto text-slate-400">
          {t.total} ticket{t.total > 1 ? 's' : ''}
        </div>
      </div>

      {/* Barre de progression tickets done */}
      {t.total > 0 && (
        <div className="w-full bg-slate-200 rounded-full h-1 overflow-hidden">
          <div className="h-1 rounded-full bg-green-500 transition-all" style={{ width: `${progressPct}%` }}/>
        </div>
      )}
    </div>
  )
}

// Labels pour le badge progress_status d'une story
const _STORY_STATUS_STYLE = {
  to_do:       { label: 'À faire',  cls: 'bg-slate-100 text-slate-600' },
  in_progress: { label: 'En cours', cls: 'bg-blue-50 text-blue-700' },
  done:        { label: 'Terminé',  cls: 'bg-green-50 text-green-700' },
}

// Tickets du consultant — groupés par projet, ordonnés par rang (priorité)
function ConsultantTicketsByProject({ projects }) {
  const projectsWithStories = (projects || []).filter(p => (p.stories || []).length > 0)
  const totalTickets = projectsWithStories.reduce((acc, p) => acc + p.stories.length, 0)

  if (projectsWithStories.length === 0) {
    return (
      <p className="text-sm text-slate-400 py-6 text-center">
        Aucun ticket actif sur tes sprints en cours.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      {projectsWithStories.map(p => {
        // Score max du projet → normalisation de la barre de priorité
        return (
          <div key={p.id} className="space-y-2">
            {/* En-tête projet */}
            <div className="flex items-center justify-between w-full">
              <div className="min-w-0">
                <div className="text-xs font-semibold text-navy truncate">{p.name}</div>
                <div className="text-[11px] text-slate-400 truncate">{p.client_name}</div>
              </div>
              <span className="text-[11px] bg-cyan-50 text-cyan-700 px-2 py-0.5 rounded-full font-medium shrink-0">
                Sprint {p.current_sprint_number}
              </span>
            </div>

            {/* Liste stories triée par rank ASC (rank 1 = plus prioritaire) */}
            <div className="space-y-1.5">
              {p.stories.map(s => {
                const status = _STORY_STATUS_STYLE[s.progress_status] || _STORY_STATUS_STYLE.to_do
                return (
                  <div
                    key={s.story_id}
                    className="flex items-center gap-2 p-2.5 bg-slate-50 hover:bg-slate-100 rounded-lg transition-colors"
                  >
                    {/* Priorité (rang) — rank 1 = plus prioritaire */}
                    <div className="flex flex-col items-center justify-center shrink-0 w-10">
                      <span className="text-[9px] text-slate-400 uppercase leading-none">Prio</span>
                      <span className={clsx(
                        'text-sm font-bold leading-tight',
                        s.is_critical ? 'text-red-600' : 'text-slate-600'
                      )}>
                        {s.rank != null ? `#${s.rank}` : '—'}
                      </span>
                    </div>

                    {/* Badge CRITIQUE si is_critical */}
                    {s.is_critical && (
                      <span className="text-[9px] font-bold text-white bg-red-500 px-1.5 py-0.5 rounded shrink-0">
                        CRITIQUE
                      </span>
                    )}

                    {/* Titre + clé Jira */}
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-slate-700 truncate">{s.title}</div>
                      {s.jira_issue_key && (
                        <div className="text-[10px] font-mono text-slate-400">{s.jira_issue_key}</div>
                      )}
                    </div>

                    {/* SP allocated / total */}
                    <span className="text-[11px] text-slate-500 shrink-0">
                      <span className="font-semibold text-slate-700">{s.allocated_sp}</span>
                      <span className="text-slate-400">/{s.story_points} sp</span>
                    </span>

                    {/* Statut */}
                    <span className={clsx('text-[10px] px-2 py-0.5 rounded-full font-medium shrink-0', status.cls)}>
                      {status.label}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      <div className="text-[11px] text-slate-400 text-right pt-1">
        {totalTickets} ticket{totalTickets > 1 ? 's' : ''} sur {projectsWithStories.length} projet{projectsWithStories.length > 1 ? 's' : ''}
      </div>
    </div>
  )
}

function ConsultantDashboard() {
  const nav = useNavigate()
  const user = useAuthStore(s => s.user)
  // Données réelles : projets actifs du consultant avec compteurs to_do/in_progress/done
  const [projectsData, setProjectsData] = useState(null)
  const [projectsLoading, setProjectsLoading] = useState(true)

  useEffect(() => {
    getConsultantDashboard()
      .then(setProjectsData)
      .catch(console.error)
      .finally(() => setProjectsLoading(false))
  }, [])

  const myProjects = projectsData?.projects ?? []

  // Tickets "ouverts" = en cours (in_progress) du sprint actif, sommés sur tous projets
  const openTickets = myProjects.reduce(
    (acc, p) => acc + (p.tickets?.in_progress ?? 0),
    0
  )

  // Tâches critiques du sprint actif (toutes statuts), sommées sur tous projets
  const criticalTickets = myProjects.reduce(
    (acc, p) => acc + (p.stories?.filter(s => s.is_critical).length ?? 0),
    0
  )

  // Solde de congés (effectif = total - pending) : récupéré via /auth/me/profile
  const leaveBalance = user?.leave_balance
  const leavePending = user?.leave_pending ?? 0
  const leaveSub = leavePending > 0
    ? `${leavePending} j en attente`
    : String(new Date().getFullYear())

  return (
    <div className="p-6 space-y-6">
      {/* Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          icon={Clock}
          label="Congés restants"
          value={leaveBalance != null ? `${leaveBalance} j` : '—'}
          color="bg-green-50 text-green-600"
          sub={leaveSub}
        />
        <MetricCard icon={TrendingUp} label="Projets actifs"
          value={projectsLoading ? '—' : myProjects.length}
          color="bg-blue-50 text-blue-600"/>
        <MetricCard
          icon={AlertCircle}
          label="Tickets Jira ouverts"
          value={projectsLoading ? '—' : openTickets}
          color="bg-amber-50 text-amber-600"
          sub="En cours sur sprint actif"
        />
        <MetricCard
          icon={AlertCircle}
          label="Tâches critiques"
          value={projectsLoading ? '—' : criticalTickets}
          color="bg-red-50 text-red-600"
          sub="dans le sprint actif"
        />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Projects — données réelles via /dashboard/consultant */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display font-bold text-navy text-base">Mes sprints courants</h3>
            {myProjects.length > 3 && (
              <button onClick={()=>nav('/chat')} className="text-xs text-cyan hover:underline flex items-center gap-1">
                Voir tout <ArrowRight size={12}/>
              </button>
            )}
          </div>
          {projectsLoading ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse"/>)}
            </div>
          ) : myProjects.length === 0 ? (
            <p className="text-sm text-slate-400 py-6 text-center">
              Aucun projet en cours.
              <span className="block text-xs mt-1">Tu n'as pas de stories sur un sprint actif.</span>
            </p>
          ) : (
            <div className="space-y-3">
              {myProjects.slice(0,3).map(p => (
                <ConsultantProjectCard key={p.id} project={p} />
              ))}
            </div>
          )}
        </div>

        {/* Tickets — groupés par projet, triés par rang (priorité) */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display font-bold text-navy text-base">Mes tickets</h3>
            <span className="text-xs text-slate-400">par priorité</span>
          </div>
          {projectsLoading ? (
            <div className="space-y-2">
              {[1,2,3,4].map(i => <div key={i} className="h-10 bg-slate-100 rounded-lg animate-pulse"/>)}
            </div>
          ) : (
            <ConsultantTicketsByProject projects={myProjects} />
          )}
        </div>
      </div>

      {/* Activity */}
      <div className="card p-5">
        <h3 className="font-display font-bold text-navy text-base mb-4">Activité récente</h3>
        <div className="space-y-3">
          {ACTIVITY.map(a => (
            <div key={a.id} className="flex items-center gap-3">
              <div className="w-2 h-2 bg-cyan rounded-full shrink-0"/>
              <div className="flex-1">
                <span className="text-sm font-medium text-slate-700">{a.action}</span>
                <span className="text-sm text-slate-400"> — {a.detail}</span>
              </div>
              <span className="text-xs text-slate-400 shrink-0">{a.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

const SKILL_LEVEL_COLOR = {
  expert:       'bg-purple-100 text-purple-700',
  advanced:     'bg-blue-100 text-blue-700',
  intermediate: 'bg-cyan-100 text-cyan-700',
  beginner:     'bg-slate-100 text-slate-500',
}

const SKILL_LEVEL_LABEL = {
  expert:       'Expert',
  advanced:     'Avancé',
  intermediate: 'Intermédiaire',
  beginner:     'Débutant',
}

function MemberSkillModal({ member, onClose }) {
  if (!member) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-5">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-navy/10 rounded-xl flex items-center justify-center shrink-0">
              <span className="text-navy text-sm font-bold">{member.initials}</span>
            </div>
            <div>
              <div className="font-semibold text-navy text-sm">{member.name}</div>
              <div className="text-xs text-slate-400">{member.job_title} · {member.team_name}</div>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
            <X size={18}/>
          </button>
        </div>

        {/* Availability badge */}
        <div className={clsx(
          'inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full mb-4',
          member.is_available ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
        )}>
          <div className={clsx('w-1.5 h-1.5 rounded-full', member.is_available ? 'bg-green-500' : 'bg-red-500')}/>
          {member.is_available ? 'Disponible aujourd\'hui' : 'En congé aujourd\'hui'}
        </div>

        {/* Projects */}
        {member.current_projects?.length > 0 && (
          <div className="mb-4">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Projets</div>
            <div className="flex flex-wrap gap-1.5">
              {member.current_projects.map(p => (
                <span key={p} className="text-xs bg-navy/5 text-navy px-2 py-0.5 rounded-full">{p}</span>
              ))}
            </div>
          </div>
        )}

        {/* Skills */}
        <div>
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 flex items-center gap-1">
            <Star size={11}/> Compétences
          </div>
          {member.skills?.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {member.skills.map((sk, i) => (
                <span key={i} className={clsx('text-xs px-2 py-0.5 rounded-full font-medium', SKILL_LEVEL_COLOR[sk.level] || 'bg-slate-100 text-slate-500')}>
                  {sk.name}
                  <span className="ml-1 opacity-60">· {SKILL_LEVEL_LABEL[sk.level] || sk.level}</span>
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-400">Aucune compétence enregistrée.</p>
          )}
        </div>
      </div>
    </div>
  )
}

function AssignedMembersCard({ count, members, loading }) {
  return (
    <div className="card p-5 relative group">
      <div className="flex items-start justify-between mb-3">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-indigo-50 text-indigo-600">
          <CheckCircle size={19} />
        </div>
      </div>
      <div className="text-2xl font-display font-bold text-navy mb-0.5">
        {loading ? '—' : count}
      </div>
      <div className="text-sm text-slate-500">Membres assignés</div>
      <div className="text-xs text-slate-400 mt-1 underline decoration-dotted underline-offset-2 cursor-default">
        Sur les sprints actifs
      </div>

      {/* Tooltip au hover */}
      {!loading && members.length > 0 && (
        <div className="
          pointer-events-none absolute left-0 top-full mt-2 z-50
          invisible opacity-0 group-hover:visible group-hover:opacity-100
          transition-opacity duration-150
          w-72 bg-white border border-slate-200 rounded-xl shadow-xl p-2 space-y-0.5
        ">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide px-2 py-1">
            {members.length} membre{members.length > 1 ? 's' : ''} sur sprint{members.length > 1 ? 's' : ''} actifs
          </div>
          {members.map((m, i) => (
            <div key={i} className="flex items-start gap-2.5 px-2 py-2 rounded-lg hover:bg-slate-50">
              {/* Avatar initiales */}
              <div className="w-8 h-8 rounded-full bg-indigo-50 text-indigo-700 flex items-center justify-center text-[10px] font-bold shrink-0">
                {(m.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-slate-800 truncate">{m.name}</div>
                <div className="text-[11px] text-slate-500 truncate">{m.job_title}</div>
                <div className="flex items-center gap-1 mt-0.5 flex-wrap">
                  <span className="text-[10px] bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded-md font-medium">
                    Sprint {m.sprint_number} · {m.project_name}
                  </span>
                  {m.department && (
                    <span className="text-[10px] text-slate-400">{m.department}</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const PM_TABS = [
  { key: 'pilotage', label: 'Pilotage projet' },
  { key: 'equipe',   label: 'Équipe / RH'     },
]

// ─── Répartition tickets par projet+sprint ──────────────────────────────────
// Affiche chaque projet en ligne : nom + sprint à gauche, chips par statut
// (À faire / En cours / Terminé) à droite. Total et critique en suffixe.
function TicketsByProjectPanel({ items }) {
  if (!items || items.length === 0) {
    return (
      <div className="card p-5 text-center text-xs text-slate-400">
        Aucun ticket sur un sprint actif.
      </div>
    )
  }
  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-3">
        <FolderKanban size={14} className="text-slate-500"/>
        <h3 className="text-sm font-semibold text-slate-700">Répartition par projet</h3>
        <span className="text-xs text-slate-400">· {items.length} projet{items.length > 1 ? 's' : ''} actif{items.length > 1 ? 's' : ''}</span>
      </div>
      <div className="space-y-2">
        {items.map(p => {
          const total = p.to_do + p.in_progress + p.done
          return (
            <div key={`${p.project_id}-${p.sprint_number}`}
                 className="flex items-center gap-3 px-3 py-2.5 bg-slate-50 rounded-lg border border-slate-100">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-slate-800 truncate">{p.project_name}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] bg-cyan-50 text-cyan-700 px-1.5 py-0.5 rounded-full font-medium">
                    Sprint {p.sprint_number}
                  </span>
                  <span className="text-[11px] text-slate-400">{total} ticket{total > 1 ? 's' : ''}</span>
                  {p.critical > 0 && (
                    <span className="inline-flex items-center gap-1 text-[10px] bg-red-50 text-red-600 px-1.5 py-0.5 rounded-full font-semibold">
                      <Flame size={9}/> {p.critical} critique{p.critical > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="text-xs px-2 py-0.5 rounded-md bg-slate-200 text-slate-700 font-medium">
                  {p.to_do} <span className="text-[10px] text-slate-500 font-normal">à faire</span>
                </span>
                <span className="text-xs px-2 py-0.5 rounded-md bg-cyan-100 text-cyan-700 font-medium">
                  {p.in_progress} <span className="text-[10px] text-cyan-600 font-normal">en cours</span>
                </span>
                <span className="text-xs px-2 py-0.5 rounded-md bg-green-100 text-green-700 font-medium">
                  {p.done} <span className="text-[10px] text-green-600 font-normal">terminé</span>
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}


function PMDashboard() {
  const [tab, setTab] = useState('pilotage')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedMember, setSelectedMember] = useState(null)
  const [events, setEvents] = useState(null)
  const [eventsLoading, setEventsLoading] = useState(true)
  const [delivery, setDelivery] = useState(null)
  const [deliveryLoading, setDeliveryLoading] = useState(true)

  useEffect(() => {
    getPMDashboard()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
    getPMEvents()
      .then(setEvents)
      .catch(console.error)
      .finally(() => setEventsLoading(false))
    getPMDelivery()
      .then(setDelivery)
      .catch(console.error)
      .finally(() => setDeliveryLoading(false))
  }, [])

  const stats          = data?.stats                  ?? {}
  const team           = data?.team_overview           ?? []
  const assignedDetail = data?.assigned_members_detail ?? []
  const avail          = stats.availability            ?? {}

  return (
    <div className="p-6 space-y-5">

      {/* ── Onglets ──────────────────────────────────────── */}
      <div className="flex gap-1 p-1 bg-slate-100 rounded-xl w-fit">
        {PM_TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'px-4 py-1.5 rounded-lg text-sm font-medium transition-all',
              tab === t.key
                ? 'bg-white text-navy shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════════════════
          ONGLET 1 — Pilotage projet
      ══════════════════════════════════════════════════ */}
      {tab === 'pilotage' && (
        <div className="space-y-6">
          {/* Ligne 1 — Projets gérés + Membres assignés */}
          <div className="grid grid-cols-2 lg:grid-cols-2 gap-4">
            <MetricCard
              icon={TrendingUp} label="Projets gérés"
              value={loading ? '—' : stats.projects_count ?? 0}
              color="bg-blue-50 text-blue-600"
            />
            <AssignedMembersCard
              count={loading ? null : stats.assigned_members_count ?? 0}
              members={assignedDetail}
              loading={loading}
            />
          </div>

          {/* Ligne 2 — Progression des tickets + Répartition par projet (même ligne) */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <h3 className="text-sm font-semibold text-slate-600">Progression des tickets</h3>
              <span className="text-xs text-slate-400">· sprint actif, tous projets confondus</span>
            </div>
            <div className="grid lg:grid-cols-[1fr_1fr_1fr_2fr] gap-4 items-start">
              <MetricCard
                icon={ListTodo} label="À faire"
                value={loading ? '—' : stats.tickets?.to_do ?? 0}
                color="bg-slate-100 text-slate-600"
                sub="Tickets non commencés"
              />
              <MetricCard
                icon={Loader2} label="En cours"
                value={loading ? '—' : stats.tickets?.in_progress ?? 0}
                color="bg-cyan-50 text-cyan-700"
                sub="Tickets en développement"
              />
              <MetricCard
                icon={CheckCircle} label="Terminé"
                value={loading ? '—' : stats.tickets?.done ?? 0}
                color="bg-green-50 text-green-600"
                sub="Tickets complétés"
              />
              {loading ? (
                <div className="space-y-2">
                  {[1,2,3].map(i => <div key={i} className="h-14 bg-slate-100 rounded-lg animate-pulse"/>)}
                </div>
              ) : (
                <TicketsByProjectPanel items={stats.tickets?.by_project ?? []} />
              )}
            </div>
          </div>

          {/* Pilotage des livraisons : statuts + projets + risques + retards + vélocité */}
          <DeliverySection data={delivery} loading={deliveryLoading} />
        </div>
      )}

      {/* ══════════════════════════════════════════════════
          ONGLET 2 — Équipe / RH
      ══════════════════════════════════════════════════ */}
      {tab === 'equipe' && (
        <div className="space-y-6">
          {/* KPIs Équipe */}
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
            <MetricCard
              icon={Users} label="Membres d'équipe"
              value={loading ? '—' : stats.team_members_count ?? 0}
              color="bg-purple-50 text-purple-600"
              sub={loading ? '' : stats.team_name ?? '—'}
            />
            <MetricCard
              icon={Circle} label="Disponibilité équipe"
              value={loading ? '—' : `${avail.percentage ?? 0}%`}
              color="bg-green-50 text-green-600"
              sub={loading ? '' : `${avail.available_count ?? 0}/${avail.total_count ?? 0} membres`}
            />
            <AssignedMembersCard
              count={loading ? null : stats.assigned_members_count ?? 0}
              members={assignedDetail}
              loading={loading}
            />
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            {/* Vue d'ensemble équipe */}
            <div className="card p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display font-bold text-navy text-base">Vue d'ensemble équipe</h3>
                <span className="text-xs text-slate-400">{team.length} membres</span>
              </div>
              {loading ? (
                <div className="space-y-2">
                  {[...Array(4)].map((_, i) => (
                    <div key={i} className="h-11 bg-slate-100 rounded-xl animate-pulse"/>
                  ))}
                </div>
              ) : team.length === 0 ? (
                <p className="text-sm text-slate-400 py-4 text-center">Aucun membre assigné pour l'instant.</p>
              ) : (
                <div className="space-y-1.5">
                  {team.map(m => (
                    <button
                      key={m.id}
                      onClick={() => setSelectedMember(m)}
                      className="w-full flex items-center gap-3 p-2.5 hover:bg-slate-50 rounded-xl transition-colors text-left"
                    >
                      <div className="w-8 h-8 bg-navy/10 rounded-lg flex items-center justify-center shrink-0">
                        <span className="text-navy text-xs font-bold">{m.initials}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-slate-800 truncate">{m.name}</div>
                        <div className="text-xs text-slate-400 truncate">
                          {m.current_projects?.length > 0 ? m.current_projects[0] : m.job_title}
                        </div>
                      </div>
                      <div className={clsx(
                        'w-2.5 h-2.5 rounded-full shrink-0',
                        m.is_available ? 'bg-green-400' : 'bg-red-400'
                      )}/>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Événements à venir */}
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-5">
                <Calendar size={17} className="text-cyan shrink-0"/>
                <h3 className="font-display font-bold text-navy text-base">Événements à venir</h3>
              </div>
              {eventsLoading ? (
                <div className="space-y-3">
                  {[...Array(3)].map((_,i) => <div key={i} className="h-16 bg-slate-100 rounded-xl animate-pulse"/>)}
                </div>
              ) : (
                <div className="space-y-4">
                  {[events?.today, events?.tomorrow].map(day => {
                    if (!day) return null
                    return (
                      <div key={day.date}>
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-xs font-bold text-slate-700 uppercase tracking-wide">{day.label}</span>
                          <span className="text-xs text-slate-400">
                            {new Date(day.date + 'T00:00:00').toLocaleDateString('fr-FR', { weekday:'long', day:'numeric', month:'long' })}
                          </span>
                          <span className="ml-auto text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
                            {day.events.length} réunion{day.events.length !== 1 ? 's' : ''}
                          </span>
                        </div>
                        {day.events.length === 0 ? (
                          <p className="text-xs text-slate-400 italic py-3 text-center border border-dashed border-slate-200 rounded-xl">
                            Aucune réunion prévue
                          </p>
                        ) : (
                          <div className="space-y-2">
                            {day.events.map(ev => (
                              <div key={ev.id} className="group flex gap-3 p-3 bg-slate-50 hover:bg-blue-50/50 rounded-xl border border-transparent hover:border-blue-100 transition-all">
                                <div className="shrink-0 text-center w-14">
                                  <div className="text-sm font-bold text-navy">{ev.start_time}</div>
                                  <div className="text-xs text-slate-400">{ev.end_time}</div>
                                  {ev.duration_min && (
                                    <div className="text-xs text-slate-400 mt-0.5">{ev.duration_min} min</div>
                                  )}
                                </div>
                                <div className="w-px bg-cyan/40 shrink-0 self-stretch rounded-full"/>
                                <div className="flex-1 min-w-0">
                                  <div className="text-sm font-semibold text-slate-800 truncate">{ev.title}</div>
                                  {ev.location && (
                                    <div className="flex items-center gap-1 mt-1 text-xs text-slate-500">
                                      <MapPin size={10} className="shrink-0"/>
                                      <span className="truncate">{ev.location}</span>
                                    </div>
                                  )}
                                  {ev.attendees?.length > 0 && (
                                    <div className="flex items-center gap-1 mt-1 text-xs text-slate-500">
                                      <UserCheck size={10} className="shrink-0"/>
                                      <span className="truncate">
                                        {ev.attendees.length === 1
                                          ? ev.attendees[0]
                                          : `${ev.attendees[0]} +${ev.attendees.length - 1}`}
                                      </span>
                                    </div>
                                  )}
                                  <div className="flex items-center gap-2 mt-2">
                                    {ev.meet_link && (
                                      <a href={ev.meet_link} target="_blank" rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 px-2 py-0.5 rounded-full transition-colors">
                                        <Video size={9}/> Rejoindre
                                      </a>
                                    )}
                                    {ev.html_link && !ev.meet_link && (
                                      <a href={ev.html_link} target="_blank" rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-navy bg-slate-100 hover:bg-slate-200 px-2 py-0.5 rounded-full transition-colors">
                                        <Calendar size={9}/> Voir
                                      </a>
                                    )}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal skills membre */}
      {selectedMember && (
        <MemberSkillModal member={selectedMember} onClose={() => setSelectedMember(null)}/>
      )}
    </div>
  )
}

export default function Dashboard() {
  const user = useAuthStore(s => s.user)
  const isPM = user?.role === 'pm'

  return (
    <div>
      <div className="px-6 pt-5 pb-2">
        <p className="text-slate-500 text-sm">
          Bonjour, <span className="font-semibold text-navy">{user?.name}</span> 👋
        </p>
      </div>
      {isPM ? <PMDashboard/> : <ConsultantDashboard/>}
    </div>
  )
}
