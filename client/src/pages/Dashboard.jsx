import { useState, useEffect } from 'react'
import { useAuthStore } from '../store'
import { PROJECTS, TICKETS, TEAM_MEMBERS, ACTIVITY } from '../data/mock'
import { TrendingUp, Clock, AlertCircle, MessageSquare, Upload, CheckCircle, Circle, ArrowRight, Users, X, Star, Calendar, MapPin, Video, UserCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import { getPMDashboard, getPMEvents } from '../api/pm'

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

function ConsultantDashboard() {
  const nav = useNavigate()
  return (
    <div className="p-6 space-y-6">
      {/* Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard icon={Clock} label="Congés restants" value="18 j" color="bg-green-50 text-green-600" sub="2025"/>
        <MetricCard icon={TrendingUp} label="Projets actifs" value="3" color="bg-blue-50 text-blue-600"/>
        <MetricCard icon={AlertCircle} label="Tickets Jira ouverts" value="7" color="bg-amber-50 text-amber-600"/>
        <MetricCard icon={MessageSquare} label="Messages non lus" value="2" color="bg-red-50 text-red-600"/>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Projects */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display font-bold text-navy text-base">Mes projets récents</h3>
            <button onClick={()=>nav('/chat')} className="text-xs text-cyan hover:underline flex items-center gap-1">
              Voir tout <ArrowRight size={12}/>
            </button>
          </div>
          <div className="space-y-3">
            {PROJECTS.slice(0,3).map(p => (
              <div key={p.id} className="p-3 bg-slate-50 rounded-xl hover:bg-slate-100 transition-colors cursor-pointer">
                <div className="flex items-start justify-between mb-1.5">
                  <div>
                    <div className="text-sm font-semibold text-slate-800">{p.name}</div>
                    <div className="text-xs text-slate-400">{p.client}</div>
                  </div>
                  <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium', STATUS_COLORS[p.status])}>
                    {p.status}
                  </span>
                </div>
                <ProgressBar value={p.progress}/>
                <div className="text-xs text-slate-400 mt-1.5">{p.progress}% · deadline {p.deadline}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Tickets */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display font-bold text-navy text-base">Mes tickets Jira</h3>
            <span className="text-xs text-slate-400">{TICKETS.length} tickets</span>
          </div>
          <div className="space-y-2">
            {TICKETS.slice(0,5).map(t => (
              <div key={t.id} className="flex items-center gap-3 p-2.5 hover:bg-slate-50 rounded-lg transition-colors cursor-pointer">
                <span className="text-xs font-mono text-slate-400 shrink-0 w-16">{t.id}</span>
                <span className="text-sm text-slate-700 flex-1 truncate">{t.title}</span>
                <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium shrink-0', PRIORITY_COLORS[t.priority])}>
                  {t.priority}
                </span>
              </div>
            ))}
          </div>
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

function PMDashboard() {
  const nav = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedMember, setSelectedMember] = useState(null)
  const [events, setEvents] = useState(null)
  const [eventsLoading, setEventsLoading] = useState(true)

  useEffect(() => {
    getPMDashboard()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
    getPMEvents()
      .then(setEvents)
      .catch(console.error)
      .finally(() => setEventsLoading(false))
  }, [])

  const stats   = data?.stats            ?? {}
  const team    = data?.team_overview    ?? []
  const columns = data?.projects_columns ?? { todo: [], in_progress: [], done: [] }
  const avail   = stats.availability    ?? {}

  const KANBAN_COLS = [
    { key: 'todo',        label: 'À faire',  accent: 'border-slate-300' },
    { key: 'in_progress', label: 'En cours', accent: 'border-cyan'      },
    { key: 'done',        label: 'Terminé',  accent: 'border-green-400' },
  ]

  return (
    <div className="p-6 space-y-6">
      {/* ── KPI Cards ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <MetricCard
          icon={TrendingUp} label="Projets gérés"
          value={loading ? '—' : stats.projects_count ?? 0}
          color="bg-blue-50 text-blue-600"
        />
        <MetricCard
          icon={Users} label="Membres d'équipe"
          value={loading ? '—' : stats.team_members_count ?? 0}
          color="bg-purple-50 text-purple-600"
          sub={loading ? '' : stats.team_name ?? '—'}
        />
        <MetricCard
          icon={CheckCircle} label="Membres assignés"
          value={loading ? '—' : stats.assigned_members_count ?? 0}
          color="bg-indigo-50 text-indigo-600"
          sub={loading ? '' : `Sur les projets actifs`}
        />
        <MetricCard
          icon={AlertCircle} label="Tickets en cours"
          value={loading ? '—' : stats.tickets_in_progress ?? 0}
          color="bg-amber-50 text-amber-600"
        />
        <MetricCard
          icon={Circle} label="Disponibilité équipe"
          value={loading ? '—' : `${avail.percentage ?? 0}%`}
          color="bg-green-50 text-green-600"
          sub={loading ? '' : `${avail.available_count ?? 0}/${avail.total_count ?? 0} membres`}
        />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* ── Vue d'ensemble équipe ─────────────────────── */}
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
                  {/* Dot disponibilité */}
                  <div className={clsx(
                    'w-2.5 h-2.5 rounded-full shrink-0',
                    m.is_available ? 'bg-green-400' : 'bg-red-400'
                  )}/>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ── Projets Kanban ────────────────────────────── */}
        <div className="card p-5">
          <h3 className="font-display font-bold text-navy text-base mb-4">Projets en cours</h3>
          {loading ? (
            <div className="grid grid-cols-3 gap-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-32 bg-slate-100 rounded-xl animate-pulse"/>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              {KANBAN_COLS.map(col => (
                <div key={col.key}>
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{col.label}</div>
                  {(columns[col.key] || []).length === 0 ? (
                    <div className="text-xs text-slate-300 italic py-2">—</div>
                  ) : (
                    (columns[col.key] || []).map(p => (
                      <div key={p.id} className={clsx('bg-slate-50 rounded-lg p-2.5 mb-2 border-l-2', col.accent)}>
                        <div className="text-xs font-medium text-slate-700 truncate">{p.name}</div>
                        <div className="text-xs text-slate-400 truncate">{p.client_name}</div>
                        {p.progress > 0 && p.progress < 100 && (
                          <div className="mt-1.5 w-full bg-slate-200 rounded-full h-1">
                            <div className="bg-cyan h-1 rounded-full" style={{ width: `${p.progress}%` }}/>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Upcoming Events ──────────────────────────────── */}
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
          <div className="grid lg:grid-cols-2 gap-6">
            {[events?.today, events?.tomorrow].map((day) => {
              if (!day) return null
              return (
                <div key={day.date}>
                  {/* Day header */}
                  <div className="flex items-center gap-2 mb-3">
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
                    <div className="space-y-2.5">
                      {day.events.map(ev => (
                        <div key={ev.id} className="group flex gap-3 p-3 bg-slate-50 hover:bg-blue-50/50 rounded-xl border border-transparent hover:border-blue-100 transition-all">
                          {/* Time column */}
                          <div className="shrink-0 text-center w-14">
                            <div className="text-sm font-bold text-navy">{ev.start_time}</div>
                            <div className="text-xs text-slate-400">{ev.end_time}</div>
                            {ev.duration_min && (
                              <div className="text-xs text-slate-400 mt-0.5">{ev.duration_min} min</div>
                            )}
                          </div>

                          {/* Separator */}
                          <div className="w-px bg-cyan/40 shrink-0 self-stretch rounded-full"/>

                          {/* Content */}
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-semibold text-slate-800 truncate">{ev.title}</div>

                            {/* Location */}
                            {ev.location && (
                              <div className="flex items-center gap-1 mt-1 text-xs text-slate-500">
                                <MapPin size={10} className="shrink-0"/>
                                <span className="truncate">{ev.location}</span>
                              </div>
                            )}

                            {/* Attendees */}
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

                            {/* Actions */}
                            <div className="flex items-center gap-2 mt-2">
                              {ev.meet_link && (
                                <a
                                  href={ev.meet_link}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 px-2 py-0.5 rounded-full transition-colors"
                                >
                                  <Video size={9}/> Rejoindre
                                </a>
                              )}
                              {ev.html_link && !ev.meet_link && (
                                <a
                                  href={ev.html_link}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-navy bg-slate-100 hover:bg-slate-200 px-2 py-0.5 rounded-full transition-colors"
                                >
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

      {/* ── CDC Upload ────────────────────────────────────── */}
      <div className="card p-5">
        <h3 className="font-display font-bold text-navy text-base mb-4">Analyser un nouveau projet</h3>
        <div
          onClick={() => nav('/nouveau-projet')}
          className="border-2 border-dashed border-slate-200 hover:border-cyan rounded-2xl p-8 text-center cursor-pointer transition-all hover:bg-cyan/5 group"
        >
          <div className="w-12 h-12 bg-slate-100 group-hover:bg-cyan/10 rounded-xl flex items-center justify-center mx-auto mb-3 transition-colors">
            <Upload size={22} className="text-slate-400 group-hover:text-cyan transition-colors"/>
          </div>
          <p className="text-sm font-medium text-slate-600 group-hover:text-navy">Déposer votre cahier des charges ici</p>
          <p className="text-xs text-slate-400 mt-1">PDF, DOCX · ou cliquez pour analyser</p>
        </div>
      </div>

      {/* ── Modal skills membre ───────────────────────────── */}
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
