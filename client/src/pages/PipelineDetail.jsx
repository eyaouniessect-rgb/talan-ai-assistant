// src/pages/PipelineDetail.jsx
// ─────────────────────────────────────────────────────────────
// Vue détaillée d'un projet — 12 phases du pipeline IA
//
// Données réelles depuis :
//   GET  /pipeline/:id          → état du projet (phases + ai_output)
//   POST /pipeline/:id/validate → { approved, feedback }
//
// Polling toutes les 4s tant qu'une phase est en cours (pending_ai).
// ─────────────────────────────────────────────────────────────

import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate }                   from 'react-router-dom'
import {
  CheckCircle, Clock, Loader, ChevronLeft,
  ThumbsUp, ThumbsDown, AlertCircle, Zap,
  FileText, Layers, GitBranch, BarChart2,
  ListChecks, Network, TrendingUp, Calendar,
  Users, Activity, ArrowRight, RefreshCw, Eye,
} from 'lucide-react'
import clsx from 'clsx'
import { getPipelineDetail, validatePhase } from '../api/pm'


// ── Mapping DB → clé courte ────────────────────────────────────
const PHASE_KEY_MAP = {
  phase_1_extraction:       'extract',
  phase_2_epics:            'epics',
  phase_3_stories:          'stories',
  phase_4_refinement:       'refinement',
  phase_5_story_deps:       'story_deps',
  phase_6_prioritization:   'prioritization',
  phase_7_tasks:            'tasks',
  phase_8_task_deps:        'task_deps',
  phase_9_critical_path:    'cpm',
  phase_10_sprint_planning: 'sprints',
  phase_11_staffing:        'staffing',
  phase_12_monitoring:      'monitoring',
}

// ── Définition des 12 phases ──────────────────────────────────
const PHASES = [
  { id: 'extract',        label: 'Extraction CDC',      icon: FileText,   desc: 'Extraction du texte brut du cahier des charges' },
  { id: 'epics',          label: 'Epics',               icon: Layers,     desc: 'Génération des epics avec stratégie de découpage' },
  { id: 'stories',        label: 'User Stories',        icon: ListChecks, desc: 'Découpage en stories + critères d\'acceptation' },
  { id: 'refinement',     label: 'Raffinement',         icon: RefreshCw,  desc: 'Débat PO ↔ Tech Lead (3 rounds + arbitre)' },
  { id: 'story_deps',     label: 'Dépendances Stories', icon: GitBranch,  desc: 'Analyse des dépendances entre User Stories' },
  { id: 'prioritization', label: 'Priorisation MoSCoW', icon: BarChart2,  desc: 'Classement valeur métier × effort' },
  { id: 'tasks',          label: 'Tasks',               icon: ListChecks, desc: 'Décomposition des stories en tâches techniques' },
  { id: 'task_deps',      label: 'Dépendances Tasks',   icon: Network,    desc: 'Graphe de dépendances entre tâches' },
  { id: 'cpm',            label: 'Chemin Critique',     icon: TrendingUp, desc: 'Critical Path Method sur toutes les tâches' },
  { id: 'sprints',        label: 'Sprint Planning',     icon: Calendar,   desc: 'Répartition des stories/tasks par sprint' },
  { id: 'staffing',       label: 'Staffing',            icon: Users,      desc: 'Affectation des tâches aux membres de l\'équipe' },
  { id: 'monitoring',     label: 'Monitoring',          icon: Activity,   desc: 'KPIs, alertes et synchronisation Jira' },
]


// ── Rendu du résultat IA selon la phase ──────────────────────
function PhaseResult({ phaseId, aiOutput }) {
  // Pour l'extraction, aiOutput peut être null (ancienne exécution) → géré dans le rendu
  if (!aiOutput && phaseId !== 'extract') return (
    <p className="text-slate-400 text-sm italic">Aucun résultat disponible pour cette phase.</p>
  )
  if (!aiOutput) aiOutput = {}

  // ── Phase 1 : Extraction ────────────────────────────────────
  if (phaseId === 'extract') {
    if (!aiOutput.pages_est && !aiOutput.chars) return (
      <div className="flex items-center gap-2 bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 text-sm">
        <CheckCircle size={15} className="shrink-0" />
        Extraction réussie — détails non disponibles (exécution précédente).
      </div>
    )
    const { filename, file_size, pages_est, chars, preview } = aiOutput
    return (
      <div className="space-y-4">
        {/* Métriques */}
        <div className="grid grid-cols-3 gap-3">
          {[
            ['Pages estimées',    pages_est ?? '—'],
            ['Caractères',        chars ? chars.toLocaleString('fr-FR') : '—'],
            ['Taille fichier',    file_size ? `${(file_size/1024).toFixed(0)} KB` : '—'],
          ].map(([k, v]) => (
            <div key={k} className="bg-slate-50 rounded-xl p-3 text-center">
              <div className="font-display font-bold text-navy text-lg">{v}</div>
              <div className="text-xs text-slate-400 mt-0.5">{k}</div>
            </div>
          ))}
        </div>

        {/* Nom du fichier */}
        {filename && (
          <div className="flex items-center gap-2 text-sm text-slate-600 bg-slate-50 rounded-xl px-3 py-2">
            <FileText size={14} className="text-cyan shrink-0" />
            <span className="font-medium truncate">{filename}</span>
          </div>
        )}

        {/* Texte extrait */}
        {preview && (
          <div>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              <Eye size={12} />
              Texte extrait (aperçu)
            </div>
            <pre className="text-xs text-slate-700 bg-slate-50 border border-slate-200 rounded-xl p-4
                            overflow-auto max-h-64 whitespace-pre-wrap leading-relaxed font-mono">
              {preview}
            </pre>
            {chars > 1500 && (
              <p className="text-xs text-slate-400 mt-1.5 text-right">
                ... {(chars - 1500).toLocaleString('fr-FR')} caractères supplémentaires
              </p>
            )}
          </div>
        )}
      </div>
    )
  }

  // ── Phase 2 : Epics ────────────────────────────────────────
  if (phaseId === 'epics') {
    const epics = aiOutput.epics ?? []
    if (!epics.length) return <p className="text-slate-400 text-sm italic">Aucun epic généré.</p>
    return (
      <div className="space-y-2">
        {epics.map((epic, i) => (
          <div key={i} className="flex items-start gap-3 p-3 bg-slate-50 rounded-xl">
            <div className="w-6 h-6 bg-navy text-white rounded-lg flex items-center justify-center text-xs font-bold shrink-0">{i+1}</div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-navy">{epic.title}</div>
              {epic.description && <div className="text-xs text-slate-500 mt-0.5">{epic.description}</div>}
              {epic.splitting_strategy && (
                <div className="text-xs text-slate-400 mt-1">
                  Stratégie : <span className="text-cyan font-medium">{epic.splitting_strategy.replace(/_/g, ' ')}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    )
  }

  // ── Phase 3 : Stories ──────────────────────────────────────
  if (phaseId === 'stories') {
    const stories = aiOutput.stories ?? []
    if (!stories.length) return <p className="text-slate-400 text-sm italic">Aucune story générée.</p>
    return (
      <div className="space-y-2">
        {stories.map((s, i) => (
          <div key={i} className="p-3 bg-slate-50 rounded-xl">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm text-slate-700">{s.title}</p>
              {s.story_points && (
                <span className="text-xs bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full shrink-0">{s.story_points} pts</span>
              )}
            </div>
            {(s.epic_id || s.splitting_strategy) && (
              <div className="flex items-center gap-3 mt-1.5">
                {s.epic_id && <span className="text-xs text-slate-400">Epic #{s.epic_id}</span>}
                {s.acceptance_criteria?.length > 0 && (
                  <span className="text-xs text-green-600">· {s.acceptance_criteria.length} critères</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    )
  }

  // ── CPM ────────────────────────────────────────────────────
  if (phaseId === 'cpm') {
    const { project_duration, critical_tasks, max_slack, critical_path } = aiOutput
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-3">
          {[
            ['Durée projet',    project_duration != null ? `${project_duration}j` : '—', 'text-navy'],
            ['Tâches critiques', critical_tasks ?? '—', 'text-red-600'],
            ['Marge max',       max_slack != null ? `${max_slack}j` : '—', 'text-green-600'],
          ].map(([k, v, cls]) => (
            <div key={k} className="bg-slate-50 rounded-xl p-3 text-center">
              <div className={clsx('font-display font-bold text-xl', cls)}>{v}</div>
              <div className="text-xs text-slate-400">{k}</div>
            </div>
          ))}
        </div>
        {critical_path?.length > 0 && (
          <div>
            <p className="text-xs font-medium text-slate-500 mb-2">Chemin critique :</p>
            <div className="flex flex-wrap items-center gap-1.5">
              {critical_path.map((t, i) => (
                <span key={i} className="flex items-center gap-1">
                  <span className="text-xs bg-red-50 text-red-700 px-2 py-0.5 rounded-full">{t}</span>
                  {i < critical_path.length - 1 && <ArrowRight size={10} className="text-slate-300" />}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  // ── Fallback générique : affichage JSON ───────────────────
  return (
    <pre className="text-xs text-slate-600 bg-slate-50 p-3 rounded-xl overflow-auto max-h-64 whitespace-pre-wrap">
      {JSON.stringify(aiOutput, null, 2)}
    </pre>
  )
}


// ── Page principale ──────────────────────────────────────────
export default function PipelineDetail() {
  const { id }  = useParams()
  const nav     = useNavigate()
  const pollRef = useRef(null)

  const [project,     setProject]     = useState(null)
  const [phaseMap,    setPhaseMap]    = useState({})   // { shortKey: phaseData }
  const [activePhase, setActivePhase] = useState(null) // shortKey
  const [loading,     setLoading]     = useState(true)
  const [error,       setError]       = useState(null)

  // Validation
  const [feedback,     setFeedback]     = useState('')
  const [showFeedback, setShowFeedback] = useState(false)
  const [submitting,   setSubmitting]   = useState(false)
  const [valError,     setValError]     = useState(null)

  // ── Charger les données du projet ────────────────────────
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const data = await getPipelineDetail(id)
      setProject(data)

      // Construire un map shortKey → phase
      const map = {}
      for (const phase of data.phases) {
        const shortKey = PHASE_KEY_MAP[phase.phase] ?? phase.phase
        map[shortKey] = phase
      }
      setPhaseMap(map)

      // Phase active = première en pending_validation, sinon la dernière connue
      const pending = data.phases.find(p => p.status === 'pending_validation')
      if (pending) {
        setActivePhase(PHASE_KEY_MAP[pending.phase] ?? pending.phase)
      } else if (!activePhase) {
        // Premier chargement → montrer la dernière phase connue
        const lastPhase = data.phases[data.phases.length - 1]
        if (lastPhase) setActivePhase(PHASE_KEY_MAP[lastPhase.phase] ?? lastPhase.phase)
      }

      setError(null)
    } catch {
      setError('Impossible de charger les données du pipeline.')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [id]) // eslint-disable-line

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // ── Polling : rafraîchit tant qu'une phase est en cours ──
  useEffect(() => {
    if (!project) return

    const hasRunning = project.phases.some(p =>
      p.status === 'pending_ai' || p.status === 'in_progress'
    )
    if (hasRunning) {
      pollRef.current = setInterval(() => fetchData(true), 4000)
    } else {
      clearInterval(pollRef.current)
    }
    return () => clearInterval(pollRef.current)
  }, [project, fetchData])

  // ── Validation ────────────────────────────────────────────
  const handleValidate = async (approved) => {
    if (!approved && !feedback.trim()) {
      setShowFeedback(true)
      return
    }
    setSubmitting(true)
    setValError(null)
    try {
      await validatePhase(id, { approved, feedback: feedback || null })
      setFeedback('')
      setShowFeedback(false)
      await fetchData()
    } catch (e) {
      setValError(e.response?.data?.detail || 'Erreur lors de la validation.')
    } finally {
      setSubmitting(false)
    }
  }

  // ── Statut d'une phase ────────────────────────────────────
  const getPhaseStatus = (shortKey) => {
    const phase = phaseMap[shortKey]
    if (!phase) return 'pending'
    if (phase.status === 'validated')          return 'done'
    if (phase.status === 'pending_validation') return 'active'
    if (phase.status === 'pending_ai')         return 'running'
    if (phase.status === 'rejected')           return 'rejected'
    return 'pending'
  }

  // ── Statut global ─────────────────────────────────────────
  const globalStatus = (() => {
    if (!project) return null
    if (project.phases.length === 0) return 'not_started'
    const hasPending = project.phases.some(p => p.status === 'pending_validation')
    const hasRunning = project.phases.some(p => p.status === 'pending_ai')
    const allDone    = project.phases.length === 12 && project.phases.every(p => p.status === 'validated')
    if (allDone)    return 'completed'
    if (hasPending) return 'pending_human'
    if (hasRunning) return 'running'
    return 'in_progress'
  })()

  // ── Skeleton ──────────────────────────────────────────────
  if (loading) return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="h-5 w-32 bg-slate-100 rounded animate-pulse mb-6" />
      <div className="h-8 w-64 bg-slate-100 rounded animate-pulse mb-2" />
      <div className="h-4 w-48 bg-slate-100 rounded animate-pulse mb-8" />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="card p-4 animate-pulse h-96" />
        <div className="lg:col-span-2 card p-5 animate-pulse h-96" />
      </div>
    </div>
  )

  if (error) return (
    <div className="p-6 max-w-6xl mx-auto">
      <button onClick={() => nav('/mes-projets')} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-navy mb-5">
        <ChevronLeft size={16} /> Mes projets
      </button>
      <div className="flex items-center gap-3 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3">
        <AlertCircle size={16} className="shrink-0" />
        {error}
      </div>
    </div>
  )

  const activePhaseData  = PHASES.find(p => p.id === activePhase)
  const activePhaseDb    = phaseMap[activePhase]
  const isPendingHuman   = activePhase && phaseMap[activePhase]?.status === 'pending_validation'

  return (
    <div className="p-6 max-w-6xl mx-auto">

      {/* Navigation retour */}
      <button onClick={() => nav('/mes-projets')} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-navy mb-5 transition-colors">
        <ChevronLeft size={16} />
        Mes projets
      </button>

      {/* En-tête projet */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="font-display font-bold text-navy text-2xl">{project?.project_name}</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Pipeline IA · {project?.phases.length ?? 0} / 12 phases enregistrées
          </p>
        </div>
        {globalStatus === 'pending_human' && (
          <span className="text-xs bg-amber-50 text-amber-600 border border-amber-200 px-3 py-1.5 rounded-full font-medium flex items-center gap-1.5">
            <AlertCircle size={12} /> Validation requise
          </span>
        )}
        {globalStatus === 'running' && (
          <span className="text-xs bg-blue-50 text-blue-600 border border-blue-200 px-3 py-1.5 rounded-full font-medium flex items-center gap-1.5">
            <Loader size={12} className="animate-spin" /> En cours...
          </span>
        )}
        {globalStatus === 'completed' && (
          <span className="text-xs bg-green-50 text-green-600 border border-green-200 px-3 py-1.5 rounded-full font-medium flex items-center gap-1.5">
            <CheckCircle size={12} /> Terminé
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* ── Colonne gauche : liste des 12 phases ─────────── */}
        <div className="lg:col-span-1">
          <div className="card p-4">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Phases du pipeline</h3>
            <div className="space-y-1">
              {PHASES.map((phase, index) => {
                const status   = getPhaseStatus(phase.id)
                const isActive = activePhase === phase.id
                const Icon     = phase.icon
                const clickable = status !== 'pending'

                return (
                  <button
                    key={phase.id}
                    onClick={() => clickable && setActivePhase(phase.id)}
                    disabled={!clickable}
                    className={clsx(
                      'w-full flex items-center gap-3 p-2.5 rounded-xl text-left transition-all',
                      isActive   ? 'bg-navy text-white' :
                      status === 'done'   ? 'hover:bg-slate-50 text-slate-600' :
                      status === 'active' ? 'hover:bg-amber-50 text-slate-700' :
                      status === 'running'? 'hover:bg-blue-50 text-slate-700' :
                      status === 'rejected' ? 'hover:bg-red-50 text-slate-600' :
                      'text-slate-300 cursor-default'
                    )}
                  >
                    <div className="shrink-0">
                      {status === 'done'    && <CheckCircle size={16} className={isActive ? 'text-green-300' : 'text-green-500'} />}
                      {status === 'active'  && <AlertCircle size={16} className={isActive ? 'text-amber-200' : 'text-amber-500'} />}
                      {status === 'running' && <Loader      size={16} className={clsx('animate-spin', isActive ? 'text-blue-300' : 'text-blue-500')} />}
                      {status === 'rejected'&& <AlertCircle size={16} className={isActive ? 'text-red-300' : 'text-red-500'} />}
                      {status === 'pending' && <Clock       size={16} className="text-slate-300" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={clsx('text-xs font-bold', isActive ? 'text-white/60' : 'text-slate-400')}>{index + 1}.</span>
                        <span className={clsx('text-sm font-medium truncate', isActive ? 'text-white' : '')}>{phase.label}</span>
                      </div>
                    </div>
                    <Icon size={14} className={clsx('shrink-0', isActive ? 'text-white/50' : 'text-slate-300')} />
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {/* ── Colonne droite : résultat IA + validation ────── */}
        <div className="lg:col-span-2 space-y-4">

          {/* Message si pipeline pas encore démarré */}
          {project?.phases.length === 0 && (
            <div className="card p-8 text-center text-slate-400">
              <Loader size={28} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">Le pipeline n'a pas encore démarré pour ce projet.</p>
            </div>
          )}

          {/* En-tête de la phase active */}
          {activePhaseData && (
            <div className="card p-5">
              <div className="flex items-start justify-between mb-1">
                <div className="flex items-center gap-2">
                  <activePhaseData.icon size={18} className="text-cyan" />
                  <h2 className="font-display font-bold text-navy text-base">{activePhaseData.label}</h2>
                </div>

                {/* Badge statut */}
                {getPhaseStatus(activePhase) === 'done' && (
                  <span className="flex items-center gap-1 text-xs text-green-600 bg-green-50 px-2.5 py-1 rounded-full">
                    <CheckCircle size={11} /> Validé
                  </span>
                )}
                {getPhaseStatus(activePhase) === 'active' && (
                  <span className="flex items-center gap-1 text-xs text-amber-600 bg-amber-50 px-2.5 py-1 rounded-full">
                    <AlertCircle size={11} /> En attente
                  </span>
                )}
                {getPhaseStatus(activePhase) === 'running' && (
                  <span className="flex items-center gap-1 text-xs text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full">
                    <Loader size={11} className="animate-spin" /> En cours...
                  </span>
                )}
                {getPhaseStatus(activePhase) === 'rejected' && (
                  <span className="flex items-center gap-1 text-xs text-red-600 bg-red-50 px-2.5 py-1 rounded-full">
                    <AlertCircle size={11} /> Rejeté
                  </span>
                )}
              </div>

              <p className="text-xs text-slate-400 mb-4">{activePhaseData.desc}</p>

              {/* Résultat IA */}
              {getPhaseStatus(activePhase) === 'running' ? (
                <div className="flex items-center gap-3 text-blue-600 text-sm py-4">
                  <Loader size={18} className="animate-spin shrink-0" />
                  L'IA traite cette phase...
                </div>
              ) : (
                <PhaseResult phaseId={activePhase} aiOutput={activePhaseDb?.ai_output} />
              )}

              {/* Timestamp */}
              {activePhaseDb?.updated_at && (
                <p className="text-xs text-slate-400 mt-4">
                  Mis à jour : {new Date(activePhaseDb.updated_at).toLocaleString('fr-FR')}
                </p>
              )}
            </div>
          )}

          {/* Zone de validation (phase en pending_validation) */}
          {isPendingHuman && (
            <div className="card p-5 border-2 border-amber-200">
              <div className="flex items-center gap-2 mb-4">
                <Zap size={16} className="text-amber-500" />
                <h3 className="font-medium text-slate-800 text-sm">Votre validation est requise</h3>
              </div>

              {showFeedback && (
                <div className="mb-4">
                  <label className="text-xs font-medium text-slate-600 block mb-1.5">
                    Feedback pour l'IA <span className="text-red-500">(obligatoire)</span>
                  </label>
                  <textarea
                    value={feedback}
                    onChange={e => setFeedback(e.target.value)}
                    placeholder="Ex: Les epics sont trop larges, découpez davantage..."
                    rows={3}
                    className="w-full text-sm border border-slate-200 rounded-xl px-3 py-2.5
                               focus:outline-none focus:ring-2 focus:ring-amber-200 focus:border-amber-400 resize-none"
                  />
                </div>
              )}

              {valError && (
                <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl px-3 py-2 mb-3">
                  <AlertCircle size={13} className="shrink-0" />
                  {valError}
                </div>
              )}

              <div className="flex gap-3">
                <button
                  onClick={() => handleValidate(false)}
                  disabled={submitting || (showFeedback && !feedback.trim())}
                  className={clsx(
                    'flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all',
                    'border border-red-200 text-red-600 hover:bg-red-50',
                    (submitting || (showFeedback && !feedback.trim())) && 'opacity-50 cursor-not-allowed'
                  )}
                >
                  <ThumbsDown size={15} />
                  {showFeedback ? 'Confirmer le rejet' : 'Rejeter'}
                </button>

                <button
                  onClick={() => handleValidate(true)}
                  disabled={submitting}
                  className={clsx(
                    'flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all',
                    'bg-navy text-white hover:bg-navy/90',
                    submitting && 'opacity-70 cursor-not-allowed'
                  )}
                >
                  {submitting ? <Loader size={15} className="animate-spin" /> : <ThumbsUp size={15} />}
                  {submitting ? 'Envoi...' : 'Approuver et continuer'}
                </button>
              </div>
            </div>
          )}

          {/* Info : pipeline terminé */}
          {globalStatus === 'completed' && (
            <div className="card p-4 border border-green-200 bg-green-50 flex items-center gap-3">
              <CheckCircle size={20} className="text-green-500 shrink-0" />
              <div>
                <p className="text-sm font-medium text-green-800">Pipeline terminé</p>
                <p className="text-xs text-green-600">Toutes les phases ont été validées.</p>
              </div>
            </div>
          )}

          {/* Info : pipeline en attente de l'IA */}
          {globalStatus === 'running' && !activePhaseDb && (
            <div className="card p-4 border border-blue-200 bg-blue-50 flex items-center gap-3">
              <Loader size={20} className="text-blue-500 animate-spin shrink-0" />
              <div>
                <p className="text-sm font-medium text-blue-800">Pipeline en cours</p>
                <p className="text-xs text-blue-600">Rafraîchissement automatique toutes les 4 secondes.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
