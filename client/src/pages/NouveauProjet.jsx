// src/pages/NouveauProjet.jsx
// ─────────────────────────────────────────────────────────────
// Wizard de création d'un nouveau projet PM (4 étapes réelles)
//
// Flux :
//   Étape 1 — Client    : sélectionner un client existant OU en créer un
//   Étape 2 — Projet    : saisir le nom du projet
//   Étape 3 — CDC       : uploader le cahier des charges (PDF/DOCX/TXT)
//   Étape 4 — Lancement : confirmer et démarrer le pipeline IA
//             → redirige vers /projet/:id
// ─────────────────────────────────────────────────────────────

import { useState, useEffect } from 'react'
import { useNavigate }         from 'react-router-dom'
import { useAuthStore }        from '../store'
import {
  Check, ChevronRight, X, Search, Plus, Building2,
  FolderPlus, Upload, CheckCircle, Loader, Rocket, AlertCircle,
} from 'lucide-react'
import clsx from 'clsx'
import {
  getClients, createClient,
  getCrmProjects, createProject,
  uploadDocument,
  startPipeline,
} from '../api/pm'

// ── Labels des étapes ─────────────────────────────────────────
const STEPS = ['Client', 'Projet', 'CDC', 'Lancement']

// ── Indicateur d'étapes ───────────────────────────────────────
function StepIndicator({ current }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {STEPS.map((label, i) => {
        const done   = current > i + 1
        const active = current === i + 1
        return (
          <div key={label} className="flex items-center gap-2">
            <div className={clsx(
              'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all',
              done   ? 'bg-green-500 text-white' :
              active ? 'bg-navy text-white' :
                       'bg-slate-200 text-slate-400'
            )}>
              {done ? <Check size={13} /> : i + 1}
            </div>
            <span className={clsx('text-sm font-medium',
              active ? 'text-navy' : done ? 'text-slate-600' : 'text-slate-300'
            )}>
              {label}
            </span>
            {i < STEPS.length - 1 && (
              <ChevronRight size={15} className="text-slate-200 mx-1" />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Composant d'erreur ────────────────────────────────────────
function ErrorBanner({ msg }) {
  if (!msg) return null
  return (
    <div className="flex items-start gap-2.5 bg-red-50 border border-red-200 text-red-700
                    text-sm rounded-xl px-4 py-3 mt-4">
      <AlertCircle size={15} className="shrink-0 mt-0.5" />
      <span>{msg}</span>
    </div>
  )
}

// ═════════════════════════════════════════════════════════════
// PAGE PRINCIPALE
// ═════════════════════════════════════════════════════════════

export default function NouveauProjet() {
  const user = useAuthStore(s => s.user)
  const nav  = useNavigate()

  // ── Guards ─────────────────────────────────────────────────
  if (user?.role !== 'pm') {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center card p-10 max-w-sm">
          <X size={24} className="text-red-500 mx-auto mb-3" />
          <h3 className="font-display font-bold text-navy text-lg mb-2">Accès refusé</h3>
          <p className="text-slate-500 text-sm mb-5">
            Réservé aux Project Managers.
          </p>
          <button onClick={() => nav('/dashboard')} className="btn-primary w-full">
            Retour au Dashboard
          </button>
        </div>
      </div>
    )
  }

  // ── State général ──────────────────────────────────────────
  const [step,    setStep]    = useState(1)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  // Données accumulées au fil du wizard
  const [selectedClient,  setSelectedClient]  = useState(null)   // { id, name }
  const [createdProject,  setCreatedProject]  = useState(null)   // { id, name }
  const [uploadedDoc,     setUploadedDoc]      = useState(null)   // { document_id, file_name }

  const next = () => { setError(null); setStep(s => s + 1) }
  const back = () => { setError(null); setStep(s => s - 1) }

  // ─────────────────────────────────────────────────────────
  // ÉTAPE 1 — CLIENT
  // ─────────────────────────────────────────────────────────
  function StepClient() {
    const [clients,    setClients]    = useState([])
    const [search,     setSearch]     = useState('')
    const [newMode,    setNewMode]    = useState(false)
    const [newName,    setNewName]    = useState('')
    const [newIndustry,setNewIndustry]= useState('')
    const [newEmail,   setNewEmail]   = useState('')
    const [fetching,   setFetching]   = useState(true)

    useEffect(() => {
      getClients()
        .then(setClients)
        .catch(() => setError('Impossible de charger les clients.'))
        .finally(() => setFetching(false))
    }, [])

    const filtered = clients.filter(c =>
      c.name.toLowerCase().includes(search.toLowerCase())
    )

    const handleSelect = (client) => {
      setSelectedClient(client)
      next()
    }

    const handleCreate = async () => {
      if (!newName.trim()) return setError('Le nom du client est obligatoire.')
      setLoading(true); setError(null)
      try {
        const client = await createClient({
          name:          newName.trim(),
          industry:      newIndustry.trim() || null,
          contact_email: newEmail.trim()    || null,
        })
        setSelectedClient(client)
        next()
      } catch (e) {
        setError(e.response?.data?.detail || 'Erreur lors de la création du client.')
      } finally {
        setLoading(false)
      }
    }

    if (fetching) return (
      <div className="flex items-center justify-center py-20">
        <Loader size={22} className="animate-spin text-cyan" />
      </div>
    )

    return (
      <div className="card p-8 space-y-5">
        <div>
          <h2 className="font-display text-xl font-bold text-navy mb-1">Sélectionner un client</h2>
          <p className="text-slate-500 text-sm">Choisissez un client existant ou créez-en un nouveau.</p>
        </div>

        {!newMode ? (
          <>
            {/* Recherche */}
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Rechercher un client..."
                className="w-full pl-9 pr-4 py-2.5 text-sm border border-slate-200 rounded-xl
                           focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan"
              />
            </div>

            {/* Liste clients */}
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {filtered.length === 0 && (
                <p className="text-sm text-slate-400 text-center py-6">Aucun client trouvé.</p>
              )}
              {filtered.map(c => (
                <button
                  key={c.id}
                  onClick={() => handleSelect(c)}
                  className="w-full flex items-center gap-3 p-3.5 rounded-xl border border-slate-200
                             hover:border-cyan/40 hover:bg-cyan/5 transition-all text-left group"
                >
                  <div className="w-9 h-9 bg-navy/5 rounded-xl flex items-center justify-center shrink-0
                                  group-hover:bg-cyan/10 transition-colors">
                    <Building2 size={16} className="text-navy/60 group-hover:text-cyan transition-colors" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-navy truncate">{c.name}</div>
                    {c.industry && <div className="text-xs text-slate-400">{c.industry}</div>}
                  </div>
                  <ChevronRight size={14} className="text-slate-300 group-hover:text-cyan transition-colors shrink-0" />
                </button>
              ))}
            </div>

            <button
              onClick={() => { setNewMode(true); setError(null) }}
              className="btn-secondary w-full flex items-center justify-center gap-2"
            >
              <Plus size={15} />
              Nouveau client
            </button>
          </>
        ) : (
          /* Formulaire nouveau client */
          <div className="space-y-3">
            <div>
              <label className="text-xs font-semibold text-slate-600 mb-1 block">
                Nom du client <span className="text-red-500">*</span>
              </label>
              <input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="ex: Talan Tunisie"
                className="input w-full"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 mb-1 block">Secteur</label>
              <input
                value={newIndustry}
                onChange={e => setNewIndustry(e.target.value)}
                placeholder="ex: Finance, Energie, Santé..."
                className="input w-full"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 mb-1 block">Email de contact</label>
              <input
                type="email"
                value={newEmail}
                onChange={e => setNewEmail(e.target.value)}
                placeholder="contact@client.com"
                className="input w-full"
              />
            </div>

            <ErrorBanner msg={error} />

            <div className="flex gap-3 pt-1">
              <button onClick={() => { setNewMode(false); setError(null) }} className="btn-secondary flex-1">
                Annuler
              </button>
              <button onClick={handleCreate} disabled={loading || !newName.trim()}
                className={clsx('btn-primary flex-1 flex items-center justify-center gap-2',
                  (!newName.trim() || loading) && 'opacity-50 cursor-not-allowed')}>
                {loading ? <Loader size={15} className="animate-spin" /> : <Plus size={15} />}
                Créer le client
              </button>
            </div>
          </div>
        )}

        {!newMode && <ErrorBanner msg={error} />}
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────
  // ÉTAPE 2 — PROJET
  // ─────────────────────────────────────────────────────────
  function StepProjet() {
    const [name,     setName]     = useState('')
    const [existing, setExisting] = useState([])
    const [fetching, setFetching] = useState(true)

    useEffect(() => {
      getCrmProjects(selectedClient.id)
        .then(setExisting)
        .catch(() => {})
        .finally(() => setFetching(false))
    }, [])

    const handleSelect = (project) => {
      setCreatedProject(project)
      next()
    }

    const handleCreate = async () => {
      if (!name.trim()) return setError('Le nom du projet est obligatoire.')
      setLoading(true); setError(null)
      try {
        const project = await createProject({ name: name.trim(), client_id: selectedClient.id })
        setCreatedProject(project)
        next()
      } catch (e) {
        const detail = e.response?.data?.detail
        // Doublon détecté côté serveur → proposer de réutiliser le projet existant
        if (e.response?.status === 409 && detail?.project_id) {
          setCreatedProject({ id: detail.project_id, name: detail.project_name })
          next()
        } else {
          setError(typeof detail === 'string' ? detail : detail?.detail || 'Erreur lors de la création du projet.')
        }
      } finally {
        setLoading(false)
      }
    }

    return (
      <div className="card p-8 space-y-5">
        <div>
          <h2 className="font-display text-xl font-bold text-navy mb-1">Projet</h2>
          <p className="text-slate-500 text-sm">
            Client : <strong className="text-navy">{selectedClient?.name}</strong>
          </p>
        </div>

        {/* Projets existants pour ce client */}
        {!fetching && existing.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              Projets existants — continuer sur un projet existant
            </p>
            <div className="space-y-2 max-h-44 overflow-y-auto">
              {existing.map(p => (
                <button
                  key={p.id}
                  onClick={() => handleSelect(p)}
                  className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-200
                             hover:border-cyan/40 hover:bg-cyan/5 transition-all text-left group"
                >
                  <div className="w-8 h-8 bg-navy/5 rounded-lg flex items-center justify-center shrink-0
                                  group-hover:bg-cyan/10 transition-colors">
                    <FolderPlus size={14} className="text-navy/60 group-hover:text-cyan" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-navy truncate">{p.name}</div>
                    <div className="text-xs text-slate-400">{p.status}</div>
                  </div>
                  <ChevronRight size={13} className="text-slate-300 group-hover:text-cyan shrink-0" />
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3 my-3">
              <div className="flex-1 h-px bg-slate-200" />
              <span className="text-xs text-slate-400">ou créer un nouveau</span>
              <div className="flex-1 h-px bg-slate-200" />
            </div>
          </div>
        )}

        {/* Nouveau projet */}
        <div>
          <label className="text-xs font-semibold text-slate-600 mb-1 block">
            Nom du nouveau projet <span className="text-red-500">*</span>
          </label>
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCreate()}
            placeholder="ex: Plateforme e-commerce"
            className="input w-full text-base"
            autoFocus
          />
        </div>

        <ErrorBanner msg={error} />

        <div className="flex gap-3">
          <button onClick={back} className="btn-secondary flex-1">Retour</button>
          <button onClick={handleCreate} disabled={loading || !name.trim()}
            className={clsx('btn-primary flex-1 flex items-center justify-center gap-2',
              (!name.trim() || loading) && 'opacity-50 cursor-not-allowed')}>
            {loading ? <Loader size={15} className="animate-spin" /> : <FolderPlus size={15} />}
            Créer le projet
          </button>
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────
  // ÉTAPE 3 — CDC (upload)
  // ─────────────────────────────────────────────────────────
  function StepCDC() {
    const [file,     setFile]     = useState(null)
    const [dragging, setDragging] = useState(false)

    const handleFile = (f) => {
      if (!f) return
      const ext = f.name.split('.').pop().toLowerCase()
      if (!['pdf', 'docx', 'txt'].includes(ext)) {
        return setError('Format non supporté. Envoyez un PDF, DOCX ou TXT.')
      }
      if (f.size > 10 * 1024 * 1024) {
        return setError('Fichier trop volumineux. Maximum 10 MB.')
      }
      setError(null)
      setFile(f)
    }

    const handleUpload = async () => {
      if (!file) return
      setLoading(true); setError(null)
      try {
        const doc = await uploadDocument(createdProject.id, file)
        setUploadedDoc(doc)
        next()
      } catch (e) {
        const detail = e.response?.data?.detail
        // Doublon : le document existe déjà → on peut quand même continuer
        if (e.response?.status === 409 && detail?.document_id) {
          setUploadedDoc({ document_id: detail.document_id, file_name: detail.file_name })
          next()
        } else {
          setError(typeof detail === 'string' ? detail : 'Erreur lors de l\'upload.')
        }
      } finally {
        setLoading(false)
      }
    }

    return (
      <div className="card p-8 space-y-5">
        <div>
          <h2 className="font-display text-xl font-bold text-navy mb-1">Uploader le cahier des charges</h2>
          <p className="text-slate-500 text-sm">
            Projet : <strong className="text-navy">{createdProject?.name}</strong>
          </p>
        </div>

        {/* Zone de drop */}
        <div
          onDrop={e => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]) }}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          className={clsx(
            'border-2 border-dashed rounded-2xl p-12 text-center transition-all cursor-pointer',
            dragging    ? 'border-cyan bg-cyan/5' :
            file        ? 'border-green-400 bg-green-50' :
                          'border-slate-200 hover:border-slate-300'
          )}
          onClick={() => !file && document.getElementById('cdc-file-input').click()}
        >
          {file ? (
            <>
              <CheckCircle size={36} className="text-green-500 mx-auto mb-3" />
              <p className="font-semibold text-green-700">{file.name}</p>
              <p className="text-xs text-green-500 mt-1">{(file.size / 1024).toFixed(0)} KB</p>
              <button
                onClick={e => { e.stopPropagation(); setFile(null); setError(null) }}
                className="text-xs text-slate-400 underline mt-2 hover:text-red-500"
              >
                Changer de fichier
              </button>
            </>
          ) : (
            <>
              <Upload size={36} className="text-slate-300 mx-auto mb-3" />
              <p className="text-slate-600 font-medium">Déposez votre fichier ici</p>
              <p className="text-xs text-slate-400 mt-1 mb-4">PDF, DOCX, TXT · max 10 MB</p>
              <span className="btn-secondary text-sm">Parcourir</span>
            </>
          )}
        </div>
        <input
          id="cdc-file-input"
          type="file"
          accept=".pdf,.docx,.txt"
          className="hidden"
          onChange={e => handleFile(e.target.files[0])}
        />

        <ErrorBanner msg={error} />

        <div className="flex gap-3">
          <button onClick={back} className="btn-secondary flex-1">Retour</button>
          <button onClick={handleUpload} disabled={loading || !file}
            className={clsx('btn-primary flex-1 flex items-center justify-center gap-2',
              (!file || loading) && 'opacity-50 cursor-not-allowed')}>
            {loading ? <Loader size={15} className="animate-spin" /> : <Upload size={15} />}
            Uploader le CDC
          </button>
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────
  // ÉTAPE 4 — LANCEMENT
  // ─────────────────────────────────────────────────────────
  function StepLancement() {
    const [jiraKey, setJiraKey] = useState('')

    const handleStart = async () => {
      setLoading(true); setError(null)
      try {
        await startPipeline(createdProject.id, {
          document_id:      uploadedDoc.document_id,
          jira_project_key: jiraKey.trim() || '',
        })
        nav(`/projet/${createdProject.id}`)
      } catch (e) {
        setError(e.response?.data?.detail || 'Erreur lors du lancement du pipeline.')
      } finally {
        setLoading(false)
      }
    }

    return (
      <div className="card p-8 space-y-5">
        <div>
          <h2 className="font-display text-xl font-bold text-navy mb-1">Lancer le pipeline IA</h2>
          <p className="text-slate-500 text-sm">Vérifiez les informations avant de démarrer l'analyse.</p>
        </div>

        {/* Récapitulatif */}
        <div className="bg-slate-50 rounded-2xl p-5 space-y-3">
          {[
            { label: 'Client',   value: selectedClient?.name },
            { label: 'Projet',   value: createdProject?.name },
            { label: 'Fichier',  value: uploadedDoc?.file_name },
          ].map(({ label, value }) => (
            <div key={label} className="flex justify-between text-sm">
              <span className="text-slate-500">{label}</span>
              <span className="font-semibold text-navy">{value}</span>
            </div>
          ))}
        </div>

        {/* Clé Jira (optionnel) */}
        <div>
          <label className="text-xs font-semibold text-slate-600 mb-1 block">
            Clé Jira <span className="text-slate-400 font-normal">(optionnel)</span>
          </label>
          <input
            value={jiraKey}
            onChange={e => setJiraKey(e.target.value)}
            placeholder="ex: TALAN-2024"
            className="input w-full"
          />
          <p className="text-xs text-slate-400 mt-1">
            Le pipeline synchronisera automatiquement les résultats avec Jira après chaque validation.
          </p>
        </div>

        <ErrorBanner msg={error} />

        <div className="flex gap-3">
          <button onClick={back} disabled={loading} className="btn-secondary flex-1">Retour</button>
          <button onClick={handleStart} disabled={loading}
            className={clsx('btn-primary flex-1 flex items-center justify-center gap-2',
              loading && 'opacity-75 cursor-not-allowed')}>
            {loading
              ? <><Loader size={15} className="animate-spin" /> Lancement...</>
              : <><Rocket size={15} /> Lancer l'analyse IA</>
            }
          </button>
        </div>
      </div>
    )
  }

  // ── Rendu ─────────────────────────────────────────────────
  return (
    <div className="p-6 max-w-2xl mx-auto">
      <StepIndicator current={step} />
      {step === 1 && <StepClient />}
      {step === 2 && <StepProjet />}
      {step === 3 && <StepCDC />}
      {step === 4 && <StepLancement />}
    </div>
  )
}
