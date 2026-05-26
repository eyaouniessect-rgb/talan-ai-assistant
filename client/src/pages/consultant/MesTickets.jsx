// src/pages/consultant/MesTickets.jsx
// ═══════════════════════════════════════════════════════════════
// Page "Mes tickets" du consultant.
// Arborescence : Projet → Sprint → Tickets
// Le consultant peut changer le progress_status (to_do / in_progress / done)
// d'un de ses tickets directement.
// ═══════════════════════════════════════════════════════════════

import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import { FolderOpen, Calendar, ChevronDown, ChevronRight, Loader2, Lock } from 'lucide-react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { getConsultantTickets, updateConsultantTicketStatus } from '../../api/pm'

const STATUS_OPTIONS = [
  { value: 'to_do',       label: 'À faire',  cls: 'bg-slate-100 text-slate-700 hover:bg-slate-200' },
  { value: 'in_progress', label: 'En cours', cls: 'bg-blue-100  text-blue-700  hover:bg-blue-200'  },
  { value: 'done',        label: 'Terminé',  cls: 'bg-green-100 text-green-700 hover:bg-green-200' },
]

const STATUS_LABEL = Object.fromEntries(STATUS_OPTIONS.map(o => [o.value, o.label]))

function _fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const months = ['jan','fév','mar','avr','mai','jun','jul','aoû','sep','oct','nov','déc']
  return `${d.getDate()} ${months[d.getMonth()]}`
}

// ──────────────────────────────────────────────────────────────
// Bouton de changement de statut (dropdown)
// disabled : pendant un PATCH en vol (spinner)
// locked   : modification interdite (sprint non-actif) → curseur not-allowed + cadenas + tooltip
// ──────────────────────────────────────────────────────────────
function StatusButton({ value, onChange, disabled, locked, lockTooltip }) {
  const [open, setOpen] = useState(false)
  const current = STATUS_OPTIONS.find(o => o.value === value) || STATUS_OPTIONS[0]
  const isBlocked = disabled || locked

  return (
    <div className="relative">
      <button
        type="button"
        disabled={isBlocked}
        title={locked ? lockTooltip : undefined}
        onClick={() => !locked && setOpen(o => !o)}
        className={clsx(
          'text-xs px-2.5 py-1 rounded-full font-medium transition-colors flex items-center gap-1',
          locked ? 'bg-slate-50 text-slate-400 border border-slate-200 cursor-not-allowed' : current.cls,
          disabled && !locked && 'opacity-60 cursor-wait'
        )}
      >
        {locked
          ? <Lock size={11} className="text-slate-400"/>
          : disabled ? <Loader2 size={12} className="animate-spin"/> : null}
        <span>{current.label}</span>
        {!locked && <ChevronDown size={12}/>}
      </button>

      {open && !isBlocked && (
        <>
          {/* overlay pour fermer au clic ailleurs */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)}/>
          <div className="absolute right-0 top-full mt-1 z-20 bg-white border border-slate-200 rounded-lg shadow-lg py-1 min-w-[140px]">
            {STATUS_OPTIONS.map(opt => (
              <button
                key={opt.value}
                type="button"
                onClick={() => { setOpen(false); if (opt.value !== value) onChange(opt.value) }}
                className={clsx(
                  'w-full text-left text-xs px-3 py-1.5 transition-colors',
                  opt.value === value
                    ? 'bg-slate-50 text-slate-400 cursor-default'
                    : 'hover:bg-slate-50 text-slate-700'
                )}
              >
                {opt.label}
                {opt.value === value && <span className="ml-1 text-[10px]">(actuel)</span>}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// Carte ticket
// ──────────────────────────────────────────────────────────────
function TicketRow({ ticket, sprintActive, onStatusChange, updating }) {
  const lockReason = sprintActive
    ? null
    : 'Le statut ne peut être modifié que pendant un sprint actif.'

  return (
    <div className="flex items-center gap-3 p-3 bg-white border border-slate-100 rounded-lg hover:border-slate-200 transition-colors">
      {/* Rang (priorité) */}
      <div className="flex flex-col items-center justify-center shrink-0 w-10">
        <span className="text-[9px] text-slate-400 uppercase leading-none">Prio</span>
        <span className={clsx(
          'text-sm font-bold leading-tight',
          ticket.is_critical ? 'text-red-600' : 'text-slate-600'
        )}>
          {ticket.rank != null ? `#${ticket.rank}` : '—'}
        </span>
      </div>

      {/* Badge CRITIQUE */}
      {ticket.is_critical && (
        <span className="text-[9px] font-bold text-white bg-red-500 px-1.5 py-0.5 rounded shrink-0">
          CRITIQUE
        </span>
      )}

      {/* Titre + clé Jira + profil */}
      <div className="flex-1 min-w-0">
        <div className="text-sm text-slate-800 truncate">{ticket.title}</div>
        <div className="flex items-center gap-2 text-[11px] text-slate-400 flex-wrap">
          {ticket.jira_issue_key && (
            <span className="font-mono">{ticket.jira_issue_key}</span>
          )}
          {ticket.required_profile && (
            <span className="px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600 font-medium text-[10px]">
              {ticket.required_profile}
              {ticket.required_level ? ` · ${ticket.required_level}` : ''}
            </span>
          )}
          <span>{ticket.allocated_sp}/{ticket.story_points} sp</span>
        </div>
      </div>

      {/* Statut + bouton de changement (locked si sprint pas actif) */}
      <StatusButton
        value={ticket.progress_status}
        onChange={s => onStatusChange(ticket.assignment_id, s)}
        disabled={updating}
        locked={!sprintActive}
        lockTooltip={lockReason}
      />
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// Bloc Sprint (collapsible)
// ──────────────────────────────────────────────────────────────
function SprintBlock({ sprint, onStatusChange, updatingId }) {
  const [open, setOpen] = useState(sprint.status === 'active')
  const counts = sprint.tickets.reduce((acc, t) => {
    acc[t.progress_status] = (acc[t.progress_status] || 0) + 1
    return acc
  }, {})

  const sprintActive = sprint.status === 'active'
  const statusColor = sprint.status === 'active'
    ? 'bg-cyan-50 text-cyan-700'
    : sprint.status === 'completed'
      ? 'bg-green-50 text-green-700'
      : 'bg-slate-100 text-slate-500'

  // Message d'info expliquant pourquoi la modification est désactivée
  const lockNotice = sprintActive
    ? null
    : sprint.status === 'planned'
      ? 'Sprint pas encore démarré — modification du statut impossible.'
      : sprint.status === 'completed'
        ? 'Sprint clôturé — les statuts sont gelés.'
        : `Sprint au statut "${sprint.status}" — modification désactivée.`

  return (
    <div className="ml-4 border-l-2 border-slate-200 pl-4">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left mb-2 py-1 hover:opacity-80 transition-opacity"
      >
        {open ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}
        <span className="text-sm font-semibold text-slate-700">{sprint.name}</span>
        <span className={clsx('text-[10px] px-1.5 py-0.5 rounded-full font-medium', statusColor)}>
          {sprint.status}
        </span>
        <span className="flex items-center gap-1 text-[11px] text-slate-400">
          <Calendar size={11}/>
          {_fmtDate(sprint.start_date)} → {_fmtDate(sprint.end_date)}
        </span>
        <span className="ml-auto text-[11px] text-slate-400">
          {sprint.tickets.length} ticket{sprint.tickets.length > 1 ? 's' : ''}
          {' · '}
          {counts.done   || 0} terminés / {counts.in_progress || 0} en cours / {counts.to_do || 0} à faire
        </span>
      </button>

      {open && (
        <>
          {lockNotice && (
            <div className="mb-2 flex items-center gap-1.5 text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5">
              <Lock size={11}/> {lockNotice}
            </div>
          )}
          <div className="space-y-2 mb-3">
            {sprint.tickets.map(t => (
              <TicketRow
                key={t.assignment_id}
                ticket={t}
                sprintActive={sprintActive}
                updating={updatingId === t.assignment_id}
                onStatusChange={onStatusChange}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// Helpers donut
// ──────────────────────────────────────────────────────────────
const TICKET_SLICES = [
  { key: 'to_do',       label: 'À faire',  color: '#94a3b8' },
  { key: 'in_progress', label: 'En cours', color: '#00B4D8' },
  { key: 'done',        label: 'Terminé',  color: '#22c55e' },
]

const SPRINT_SLICES = [
  { key: 'active',    label: 'Actif',   color: '#00B4D8' },
  { key: 'completed', label: 'Terminé', color: '#22c55e' },
  { key: 'planned',   label: 'Planifié', color: '#94a3b8' },
]

function MiniDonut({ data, label, total }) {
  const empty = [{ key: '_', value: 1, color: '#f1f5f9' }]
  const slices = data.length ? data : empty
  return (
    <div className="card p-5 flex items-center gap-5 flex-1 min-w-[220px]">
      <div className="shrink-0" style={{ width: 110, height: 110 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              cx="50%" cy="50%"
              innerRadius={30} outerRadius={50}
              dataKey="value"
              strokeWidth={2} stroke="#fff"
            >
              {slices.map(e => <Cell key={e.key} fill={e.color} />)}
            </Pie>
            {data.length > 0 && (
              <Tooltip
                formatter={(v, n) => [v, n]}
                contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e2e8f0' }}
              />
            )}
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">{label}</div>
        <div className="text-2xl font-bold text-navy mb-2">
          {total} <span className="text-xs font-normal text-slate-400">total</span>
        </div>
        <div className="space-y-1">
          {data.map(s => (
            <div key={s.key} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
              <span className="text-xs text-slate-600 flex-1 truncate">{s.label}</span>
              <span className="text-xs font-semibold text-slate-700">{s.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// Carte tâches critiques avec tooltip au survol
// ──────────────────────────────────────────────────────────────
function CriticalTicketsCard({ tickets }) {
  return (
    <div className="card p-5 flex-1 min-w-[220px] border border-red-100 bg-red-50 flex flex-col justify-between">
      <div className="flex items-center gap-1.5 mb-2">
        <span className="w-2 h-2 rounded-full bg-red-500 shrink-0" />
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Tâches critiques</span>
      </div>
      <div className="text-3xl font-bold text-red-600">{tickets.length}</div>
      <div className="text-xs text-slate-400 mt-1">
        {tickets.length === 0 ? 'Aucune tâche critique' : `dans le sprint actif`}
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// Conteneur principal du résumé
// ──────────────────────────────────────────────────────────────
function ActiveSprintDonut({ projects }) {
  const { ticketCounts, sprintCounts, criticalTickets } = useMemo(() => {
    const tc = { to_do: 0, in_progress: 0, done: 0 }
    const sc = { active: 0, completed: 0, planned: 0 }
    const critical = []

    for (const project of projects) {
      for (const sprint of project.sprints) {
        const key = sprint.status
        if (key in sc) sc[key]++

        if (sprint.status === 'active') {
          for (const t of sprint.tickets) {
            if (t.progress_status in tc) tc[t.progress_status]++
            if (t.is_critical) {
              critical.push({ ...t, sprint_name: sprint.name, project_name: project.name })
            }
          }
        }
      }
    }
    return { ticketCounts: tc, sprintCounts: sc, criticalTickets: critical }
  }, [projects])

  const ticketTotal = ticketCounts.to_do + ticketCounts.in_progress + ticketCounts.done
  const sprintTotal = sprintCounts.active + sprintCounts.completed + sprintCounts.planned
  if (sprintTotal === 0) return null

  const ticketData = TICKET_SLICES.map(s => ({ ...s, value: ticketCounts[s.key] })).filter(d => d.value > 0)
  const sprintData  = SPRINT_SLICES.map(s => ({ ...s, value: sprintCounts[s.key]  })).filter(d => d.value > 0)

  return (
    <div className="flex gap-4 flex-wrap">
      <MiniDonut data={ticketData} label="Tickets (sprint actif)" total={ticketTotal} />
      <MiniDonut data={sprintData}  label="Répartition sprints"    total={sprintTotal} />
      <CriticalTicketsCard tickets={criticalTickets} />
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// Bloc Projet (collapsible, contient les sprints)
// ──────────────────────────────────────────────────────────────
function ProjectBlock({ project, onStatusChange, updatingId }) {
  const [open, setOpen] = useState(true)
  const totalTickets = project.sprints.reduce((acc, s) => acc + s.tickets.length, 0)

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-3">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="text-slate-400 hover:text-slate-600"
        >
          {open ? <ChevronDown size={18}/> : <ChevronRight size={18}/>}
        </button>
        <FolderOpen size={18} className="text-cyan"/>
        <div className="text-left flex-1">
          <div className="font-display font-bold text-navy text-base">{project.name}</div>
          <div className="text-xs text-slate-400">{project.client_name}</div>
        </div>
        <span className="text-xs text-slate-400">
          {totalTickets} ticket{totalTickets > 1 ? 's' : ''} · {project.sprints.length} sprint{project.sprints.length > 1 ? 's' : ''}
        </span>
      </div>

      {open && (
        <div className="space-y-3">
          {project.sprints.map(s => (
            <SprintBlock
              key={s.sprint_number}
              sprint={s}
              updatingId={updatingId}
              onStatusChange={onStatusChange}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// Page principale
// ──────────────────────────────────────────────────────────────
export default function MesTickets() {
  const nav = useNavigate()
  const [data, setData]           = useState(null)
  const [loading, setLoading]     = useState(true)
  const [updatingId, setUpdatingId] = useState(null)
  const [error, setError]         = useState(null)

  const load = () => {
    setLoading(true)
    getConsultantTickets()
      .then(setData)
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleStatusChange = async (assignmentId, newStatus) => {
    setUpdatingId(assignmentId)
    try {
      await updateConsultantTicketStatus(assignmentId, newStatus)
      // Mise à jour optimiste locale, ciblée sur l'assignment précis
      // (et non sur toutes les rows partageant le même story_id).
      setData(prev => {
        if (!prev) return prev
        return {
          ...prev,
          projects: prev.projects.map(p => ({
            ...p,
            sprints: p.sprints.map(s => ({
              ...s,
              tickets: s.tickets.map(t =>
                t.assignment_id === assignmentId ? { ...t, progress_status: newStatus } : t
              ),
            })),
          })),
        }
      })
    } catch (e) {
      alert(`Erreur lors du changement de statut : ${e.response?.data?.detail || e.message}`)
    } finally {
      setUpdatingId(null)
    }
  }

  const projects = data?.projects ?? []

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display font-bold text-navy text-xl">Mes tickets</h1>
          <p className="text-sm text-slate-500">
            Tous tes tickets, regroupés par projet et par sprint.
            Clique sur le statut pour le modifier.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1,2].map(i => <div key={i} className="card p-5 h-48 animate-pulse bg-slate-50"/>)}
        </div>
      ) : error ? (
        <div className="card p-5 text-red-600 text-sm">{error}</div>
      ) : projects.length === 0 ? (
        <div className="card p-10 text-center text-slate-400">
          <CheckSquareEmpty/>
          <p className="mt-2 text-sm">Tu n'as encore aucun ticket assigné.</p>
        </div>
      ) : (
        <div className="space-y-4">
          <ActiveSprintDonut projects={projects} />
          {projects.map(p => (
            <ProjectBlock
              key={p.id}
              project={p}
              updatingId={updatingId}
              onStatusChange={handleStatusChange}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function CheckSquareEmpty() {
  return (
    <div className="w-12 h-12 mx-auto rounded-2xl bg-slate-100 flex items-center justify-center">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="3"/>
      </svg>
    </div>
  )
}
