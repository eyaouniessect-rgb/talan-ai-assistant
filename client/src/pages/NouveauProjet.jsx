// src/pages/NouveauProjet.jsx
import { useState } from 'react'
import { useAuthStore } from '../store'
import { useNavigate } from 'react-router-dom'
import { Upload, Check, Loader, ChevronRight, CheckCircle, X } from 'lucide-react'
import clsx from 'clsx'

const PIPELINE_STEPS = [
  'Extraction du CDC',
  'Débat PO vs TL',
  'Priorisation MoSCoW',
  'Graphe de dépendances',
  'Calcul du chemin critique (CPM)',
  'Allocation des ressources',
]

const MOSCOW = {
  'Must Have': ['Authentification utilisateur', 'Module de gestion des congés', 'Dashboard analytics', 'Intégration Jira'],
  'Should Have': ['Notifications temps réel', 'Export PDF des rapports', 'Historique des conversations'],
  'Could Have': ['Mode sombre', 'Application mobile', 'Intégration Teams'],
  "Won't Have": ['IA générative vocale', 'Réalité augmentée'],
}

export default function NouveauProjet() {
  const user = useAuthStore(s => s.user)
  const nav = useNavigate()
  const [step, setStep] = useState(1)
  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState(null)

  // Accès réservé aux PM
  if (user?.role !== 'pm') {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center card p-10 max-w-sm">
          <div className="w-14 h-14 bg-red-50 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <X size={24} className="text-red-500" />
          </div>
          <h3 className="font-display font-bold text-navy text-lg mb-2">Accès refusé</h3>
          <p className="text-slate-500 text-sm mb-5">Cette fonctionnalité est réservée aux Project Managers.</p>
          <button onClick={() => nav('/dashboard')} className="btn-primary w-full">Retour au Dashboard</button>
        </div>
      </div>
    )
  }

  const startAnalysis = () => {
    if (!file) return
    setStep(2)
    let s = 0
    const interval = setInterval(() => {
      s++; setCurrentStep(s)
      setProgress(Math.round((s / PIPELINE_STEPS.length) * 100))
      if (s >= PIPELINE_STEPS.length) { clearInterval(interval); setTimeout(() => setStep(3), 600) }
    }, 900)
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Indicateur d'étapes */}
      <div className="flex items-center gap-3 mb-8">
        {['Upload CDC', 'Analyse', 'Résultats'].map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={clsx('w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold',
              step > i + 1 ? 'bg-green-500 text-white' : step === i + 1 ? 'bg-navy text-white' : 'bg-slate-200 text-slate-500')}>
              {step > i + 1 ? <Check size={13} /> : i + 1}
            </div>
            <span className={clsx('text-sm font-medium', step === i + 1 ? 'text-navy' : 'text-slate-400')}>{s}</span>
            {i < 2 && <ChevronRight size={16} className="text-slate-300 mx-1" />}
          </div>
        ))}
      </div>

      {/* Étape 1 : Upload */}
      {step === 1 && (
        <div className="card p-8">
          <h2 className="font-display text-xl font-bold text-navy mb-2">Uploader le cahier des charges</h2>
          <p className="text-slate-500 text-sm mb-6">Notre IA va analyser votre CDC et générer un plan de projet complet.</p>
          <div onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) setFile(f) }}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            className={clsx('border-2 border-dashed rounded-2xl p-12 text-center transition-all',
              dragging ? 'border-cyan bg-cyan/5' : 'border-slate-200 hover:border-slate-300',
              file && 'border-green-400 bg-green-50')}>
            {file ? (
              <>
                <CheckCircle size={36} className="text-green-500 mx-auto mb-3" />
                <p className="font-medium text-green-700">{file.name}</p>
                <p className="text-xs text-green-500 mt-1">{(file.size / 1024).toFixed(0)} KB</p>
              </>
            ) : (
              <>
                <Upload size={36} className="text-slate-300 mx-auto mb-3" />
                <p className="text-slate-600 font-medium">Déposez votre fichier ici</p>
                <p className="text-xs text-slate-400 mt-1 mb-4">PDF, DOCX · max 10 MB</p>
                <label className="btn-secondary text-sm cursor-pointer">
                  Parcourir
                  <input type="file" accept=".pdf,.docx" className="hidden" onChange={e => setFile(e.target.files[0])} />
                </label>
              </>
            )}
          </div>
          <button onClick={startAnalysis} disabled={!file}
            className={clsx('btn-primary w-full mt-4', !file && 'opacity-50 cursor-not-allowed')}>
            Lancer l'analyse IA
          </button>
        </div>
      )}

      {/* Étape 2 : Analyse en cours */}
      {step === 2 && (
        <div className="card p-8">
          <h2 className="font-display text-xl font-bold text-navy mb-2">Analyse en cours...</h2>
          <p className="text-slate-500 text-sm mb-6">{file?.name}</p>
          <div className="w-full bg-slate-100 rounded-full h-2 mb-6">
            <div className="bg-cyan h-2 rounded-full transition-all duration-700" style={{ width: `${progress}%` }} />
          </div>
          <div className="space-y-3">
            {PIPELINE_STEPS.map((s, i) => (
              <div key={s} className="flex items-center gap-3 p-3 rounded-xl bg-slate-50">
                {i < currentStep ? <CheckCircle size={18} className="text-green-500 shrink-0" />
                  : i === currentStep ? <Loader size={18} className="text-cyan animate-spin shrink-0" />
                  : <div className="w-4.5 h-4.5 rounded-full border-2 border-slate-300 shrink-0" />}
                <span className={clsx('text-sm', i < currentStep ? 'text-slate-700' : i === currentStep ? 'text-navy font-medium' : 'text-slate-400')}>{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Étape 3 : Résultats */}
      {step === 3 && (
        <div className="space-y-5 fade-in-up">
          <div className="card p-5">
            <h3 className="font-display font-bold text-navy text-base mb-4">Priorisation MoSCoW</h3>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(MOSCOW).map(([cat, items]) => (
                <div key={cat} className={clsx('p-3 rounded-xl',
                  cat === 'Must Have' ? 'bg-red-50' : cat === 'Should Have' ? 'bg-amber-50' : cat === 'Could Have' ? 'bg-blue-50' : 'bg-slate-50')}>
                  <div className="text-xs font-bold mb-2 uppercase tracking-wide text-slate-600">{cat}</div>
                  {items.map(item => <div key={item} className="text-xs text-slate-700 py-0.5">· {item}</div>)}
                </div>
              ))}
            </div>
          </div>
          <div className="card p-5">
            <h3 className="font-display font-bold text-navy text-base mb-4">Allocation recommandée</h3>
            <div className="grid grid-cols-3 gap-3">
              {[['Développeurs', 4, 'bg-blue-100 text-blue-700'], ['Designers', 1, 'bg-pink-100 text-pink-700'], ['DevOps', 1, 'bg-green-100 text-green-700']].map(([r, n, c]) => (
                <div key={r} className="text-center p-4 bg-slate-50 rounded-xl">
                  <div className={clsx('text-2xl font-display font-bold mb-1', c.split(' ')[1])}>{n}</div>
                  <div className="text-xs text-slate-500">{r}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="flex gap-3">
            <button className="btn-primary flex-1">Télécharger PDF</button>
            <button className="btn-secondary flex-1">Envoyer sur Slack</button>
          </div>
        </div>
      )}
    </div>
  )
}