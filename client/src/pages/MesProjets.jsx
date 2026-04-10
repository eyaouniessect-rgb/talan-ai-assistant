// src/pages/MesProjets.jsx
// ─────────────────────────────────────────────────────────────
// Bibliothèque des projets PM
// Connecté à GET /pipeline/projects (données réelles).
// Chaque carte → /projet/:id (PipelineDetail)
// ─────────────────────────────────────────────────────────────

import { useState, useEffect } from 'react'
import { useNavigate }         from 'react-router-dom'
import { useAuthStore }        from '../store'
import {
  Folder, Plus, Search, ChevronRight,
  Clock, CheckCircle, AlertCircle, Loader,
  Calendar, Zap,
} from 'lucide-react'
import clsx from 'clsx'
import { getPipelineProjects } from '../api/pm'

// ── Mapping phase → label lisible ───────────────────────────
const PHASE_LABELS = {
  extract:        'Extraction CDC',
  epics:          'Epics',
  stories:        'User Stories',
  refinement:     'Raffinement PO/TL',
  story_deps:     'Dépendances Stories',
  prioritization: 'Priorisation MoSCoW',
  tasks:          'Tasks',
  task_deps:      'Dépendances Tasks',
  cpm:            'Chemin Critique (CPM)',
  sprints:        'Sprint Planning',
  staffing:       'Staffing',
  monitoring:     'Monitoring',
}

// ── Badge statut ─────────────────────────────────────────────
function StatusBadge({ status }) {
  const config = {
    not_started:   { label: 'Non démarré',   icon: Clock,         cls: 'bg-slate-100 text-slate-500' },
    in_progress:   { label: 'En cours',      icon: Loader,        cls: 'bg-blue-50 text-blue-600' },
    pending_human: { label: 'Validation PM', icon: AlertCircle,   cls: 'bg-amber-50 text-amber-600' },
    completed:     { label: 'Terminé',       icon: CheckCircle,   cls: 'bg-green-50 text-green-600' },
    rejected:      { label: 'Rejeté',        icon: AlertCircle,   cls: 'bg-red-50 text-red-600' },
  }
  const { label, icon: Icon, cls } = config[status] || config.in_progress
  return (
    <span className={clsx('inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full', cls)}>
      <Icon size={11} className={status === 'in_progress' ? 'animate-spin' : ''} />
      {label}
    </span>
  )
}

// ── Barre de progression ─────────────────────────────────────
function ProgressBar({ done, total }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  return (
    <div className="mt-3">
      <div className="flex justify-between text-xs text-slate-400 mb-1.5">
        <span>Phase {done}/{total}</span>
        <span>{pct}%</span>
      </div>
      <div className="w-full bg-slate-100 rounded-full h-1.5">
        <div
          className={clsx('h-1.5 rounded-full transition-all', done === total && total > 0 ? 'bg-green-500' : 'bg-cyan')}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ── Carte projet ─────────────────────────────────────────────
function ProjectCard({ project, onClick }) {
  return (
    <button
      onClick={onClick}
      className="card p-5 text-left hover:shadow-md hover:border-cyan/30 border border-transparent
                 transition-all duration-200 w-full group"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="w-10 h-10 bg-navy/5 rounded-xl flex items-center justify-center shrink-0
                        group-hover:bg-cyan/10 transition-colors">
          <Folder size={18} className="text-navy group-hover:text-cyan transition-colors" />
        </div>
        <StatusBadge status={project.global_status} />
      </div>

      <h3 className="font-display font-bold text-navy text-sm leading-tight mb-1">
        {project.project_name}
      </h3>
      <p className="text-xs text-slate-500 mb-3">{project.client_name}</p>

      {project.global_status !== 'completed' && project.current_phase && (
        <div className="flex items-center gap-1.5 mb-1">
          <Zap size={11} className="text-cyan shrink-0" />
          <span className="text-xs text-slate-600">
            {project.global_status === 'pending_human'
              ? <>Validation requise : <strong>{PHASE_LABELS[project.current_phase]}</strong></>
              : <>Phase : <strong>{PHASE_LABELS[project.current_phase]}</strong></>
            }
          </span>
        </div>
      )}

      <ProgressBar done={project.phases_done} total={project.phases_total} />

      <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
        <div className="flex items-center gap-1 text-xs text-slate-400">
          <Calendar size={11} />
          <span>
            {project.created_at
              ? new Date(project.created_at).toLocaleDateString('fr-FR')
              : '—'}
          </span>
        </div>
        <ChevronRight size={14} className="text-slate-300 group-hover:text-cyan transition-colors" />
      </div>
    </button>
  )
}

// ── Skeleton de chargement ────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="card p-5 animate-pulse">
      <div className="flex justify-between mb-3">
        <div className="w-10 h-10 bg-slate-100 rounded-xl" />
        <div className="w-20 h-6 bg-slate-100 rounded-full" />
      </div>
      <div className="h-4 bg-slate-100 rounded w-3/4 mb-2" />
      <div className="h-3 bg-slate-100 rounded w-1/2 mb-4" />
      <div className="h-1.5 bg-slate-100 rounded-full" />
    </div>
  )
}

// ── Page principale ──────────────────────────────────────────
export default function MesProjets() {
  const user = useAuthStore(s => s.user)
  const nav  = useNavigate()

  const [projects, setProjects] = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [search,   setSearch]   = useState('')
  const [filter,   setFilter]   = useState('all')

  useEffect(() => {
    getPipelineProjects()
      .then(setProjects)
      .catch(() => setError('Impossible de charger les projets.'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = projects.filter(p => {
    const matchSearch = (p.project_name + p.client_name).toLowerCase().includes(search.toLowerCase())
    const matchFilter = filter === 'all' || p.global_status === filter
    return matchSearch && matchFilter
  })

  const counts = {
    all:           projects.length,
    pending_human: projects.filter(p => p.global_status === 'pending_human').length,
    in_progress:   projects.filter(p => p.global_status === 'in_progress').length,
    completed:     projects.filter(p => p.global_status === 'completed').length,
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">

      {/* En-tête */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display font-bold text-navy text-2xl">Mes Projets</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {loading ? '...' : `${counts.all} projet${counts.all > 1 ? 's' : ''} · pipeline IA`}
          </p>
        </div>
        <button onClick={() => nav('/nouveau-projet')} className="btn-primary flex items-center gap-2">
          <Plus size={16} />
          Nouveau projet
        </button>
      </div>

      {/* Barre filtres + recherche */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Rechercher un projet ou client..."
            className="w-full pl-9 pr-4 py-2.5 text-sm border border-slate-200 rounded-xl
                       focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan"
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          {[
            { key: 'all',           label: `Tous (${counts.all})` },
            { key: 'pending_human', label: `En attente (${counts.pending_human})` },
            { key: 'in_progress',   label: `En cours (${counts.in_progress})` },
            { key: 'completed',     label: `Terminés (${counts.completed})` },
          ].map(f => (
            <button key={f.key} onClick={() => setFilter(f.key)}
              className={clsx(
                'text-xs px-3 py-2 rounded-xl font-medium transition-all whitespace-nowrap',
                filter === f.key ? 'bg-navy text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              )}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Alerte validations en attente */}
      {counts.pending_human > 0 && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl
                        px-4 py-3 mb-5 text-sm text-amber-700">
          <AlertCircle size={16} className="shrink-0" />
          <span>
            <strong>{counts.pending_human} projet{counts.pending_human > 1 ? 's' : ''}</strong> en attente de votre validation.
          </span>
          <button onClick={() => setFilter('pending_human')}
            className="ml-auto text-xs underline underline-offset-2 hover:text-amber-900">
            Voir
          </button>
        </div>
      )}

      {/* Erreur API */}
      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-600
                        text-sm rounded-xl px-4 py-3 mb-5">
          <AlertCircle size={15} className="shrink-0" />
          {error}
        </div>
      )}

      {/* Grille */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => <SkeletonCard key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <Folder size={36} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">
            {projects.length === 0
              ? 'Aucun projet pour l\'instant. Créez votre premier projet !'
              : 'Aucun projet correspond à votre recherche.'}
          </p>
          {projects.length === 0 && (
            <button onClick={() => nav('/nouveau-projet')}
              className="btn-primary mt-4 inline-flex items-center gap-2">
              <Plus size={15} />
              Créer un projet
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(project => (
            <ProjectCard
              key={project.project_id}
              project={project}
              onClick={() => nav(`/projet/${project.project_id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
