import { useState } from 'react'
import { useChatStore, useNotifStore, useAuthStore } from '../store'
import { useNavigate } from 'react-router-dom'
import { Search, RotateCcw, Bell, CheckCheck, Upload, Check, Loader, ChevronRight, AlertTriangle, CheckCircle, Info, X } from 'lucide-react'
import clsx from 'clsx'

const AGENT_COLORS = { RH:'bg-green-100 text-green-700', CRM:'bg-blue-100 text-blue-700', Jira:'bg-orange-100 text-orange-700', Slack:'bg-purple-100 text-purple-700', Calendar:'bg-cyan-100 text-cyan-700' }

// ─── HISTORIQUE ───
export function Historique() {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('Tout')
  const [expanded, setExpanded] = useState(null)
  const { conversations, setActive } = useChatStore()
  const nav = useNavigate()
  const filters = ['Tout','Cette semaine','Ce mois','RH','CRM','Jira','Slack','Calendar']

  const filtered = conversations.filter(c => {
    const matchSearch = c.title.toLowerCase().includes(search.toLowerCase())
    const matchFilter = filter==='Tout' || c.agents.includes(filter) ||
      (filter==='Cette semaine') || (filter==='Ce mois')
    return matchSearch && matchFilter
  })

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/>
          <input className="input-field pl-9" placeholder="Rechercher dans l'historique..."
            value={search} onChange={e=>setSearch(e.target.value)}/>
        </div>
      </div>
      <div className="flex gap-2 mb-5 overflow-x-auto pb-1">
        {filters.map(f => (
          <button key={f} onClick={()=>setFilter(f)}
            className={clsx('shrink-0 text-xs px-3 py-1.5 rounded-lg font-medium transition-all',
              filter===f ? 'bg-navy text-white' : 'bg-white border border-slate-200 text-slate-600 hover:border-cyan')}>
            {f}
          </button>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-16">
          <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Search size={22} className="text-slate-400"/>
          </div>
          <p className="text-slate-500">Aucune conversation trouvée</p>
        </div>
      )}

      <div className="space-y-3">
        {filtered.map(conv => (
          <div key={conv.id} className="card overflow-hidden">
            <div className="p-4 flex items-center gap-4 cursor-pointer hover:bg-slate-50 transition-colors"
              onClick={()=>setExpanded(expanded===conv.id ? null : conv.id)}>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-800 text-sm truncate mb-1">{conv.title}</div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400">{conv.date}</span>
                  <span className="text-xs text-slate-400">{conv.messageCount} messages</span>
                  <div className="flex gap-1">
                    {conv.agents.map(a => (
                      <span key={a} className={clsx('text-xs px-1.5 py-0.5 rounded-md font-medium', AGENT_COLORS[a]||'bg-slate-100 text-slate-600')}>{a}</span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={(e)=>{e.stopPropagation(); setActive(conv.id); nav('/chat')}}
                  className="text-xs btn-secondary py-1.5 px-3 flex items-center gap-1">
                  <RotateCcw size={12}/> Reprendre
                </button>
                <ChevronRight size={16} className={clsx('text-slate-400 transition-transform', expanded===conv.id && 'rotate-90')}/>
              </div>
            </div>
            {expanded===conv.id && (
              <div className="border-t border-slate-100 p-4 bg-slate-50 space-y-3">
                {conv.messages.map((msg, i) => (
                  <div key={i} className={clsx('flex gap-2', msg.role==='user' && 'flex-row-reverse')}>
                    <div className={clsx('text-xs px-3 py-2 rounded-xl max-w-md',
                      msg.role==='user' ? 'bg-navy text-white' : 'bg-white border border-slate-200 text-slate-700')}>
                      {msg.content}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── NOTIFICATIONS ───
const NOTIF_ICONS = {
  info: <Info size={16} className="text-blue-500"/>,
  success: <CheckCircle size={16} className="text-green-500"/>,
  warning: <AlertTriangle size={16} className="text-amber-500"/>,
  error: <X size={16} className="text-red-500"/>,
}
const SOURCE_COLORS = { Jira:'bg-orange-50 text-orange-700', Slack:'bg-purple-50 text-purple-700', RH:'bg-green-50 text-green-700', Calendar:'bg-cyan-50 text-cyan-700', CRM:'bg-blue-50 text-blue-700' }

export function Notifications() {
  const [tab, setTab] = useState('Toutes')
  const { notifications, markRead, markAllRead } = useNotifStore()
  const tabs = ['Toutes','Non lues','Actions requises']
  const filtered = notifications.filter(n =>
    tab==='Non lues' ? !n.read :
    tab==='Actions requises' ? n.type==='warning' : true
  )
  const unread = notifications.filter(n=>!n.read).length

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <div className="flex gap-1">
          {tabs.map(t => (
            <button key={t} onClick={()=>setTab(t)}
              className={clsx('text-sm px-4 py-2 rounded-xl font-medium transition-all',
                tab===t ? 'bg-navy text-white' : 'text-slate-600 hover:bg-slate-100')}>
              {t} {t==='Non lues' && unread>0 && <span className="ml-1 bg-red-500 text-white text-xs w-4 h-4 rounded-full inline-flex items-center justify-center">{unread}</span>}
            </button>
          ))}
        </div>
        {unread>0 && (
          <button onClick={markAllRead} className="text-xs text-cyan hover:underline flex items-center gap-1">
            <CheckCheck size={14}/> Tout marquer comme lu
          </button>
        )}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-16">
          <Bell size={32} className="text-slate-300 mx-auto mb-3"/>
          <p className="text-slate-500">Aucune notification</p>
        </div>
      )}

      <div className="space-y-2">
        {filtered.map(n => (
          <div key={n.id} className={clsx('card p-4 flex items-start gap-3 transition-all hover:shadow-md cursor-pointer', !n.read && 'border-l-4 border-l-cyan')}
            onClick={()=>markRead(n.id)}>
            <div className="mt-0.5 shrink-0">{NOTIF_ICONS[n.type]}</div>
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2">
                <p className={clsx('text-sm font-medium', !n.read ? 'text-slate-900' : 'text-slate-700')}>{n.title}</p>
                <span className="text-xs text-slate-400 shrink-0">{n.time}</span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">{n.desc}</p>
              <div className="flex items-center gap-2 mt-2">
                <span className={clsx('text-xs px-2 py-0.5 rounded-md font-medium', SOURCE_COLORS[n.source]||'bg-slate-100 text-slate-600')}>{n.source}</span>
                {!n.read && <span className="text-xs text-slate-400">· Cliquer pour marquer comme lu</span>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── NOUVEAU PROJET (PM only) ───
const PIPELINE_STEPS = [
  'Extraction du CDC',
  'Débat PO vs TL',
  'Priorisation MoSCoW',
  'Graphe de dépendances',
  'Calcul du chemin critique (CPM)',
  'Allocation des ressources',
]
const MOSCOW = {
  'Must Have': ['Authentification utilisateur','Module de gestion des congés','Dashboard analytics','Intégration Jira'],
  'Should Have': ['Notifications temps réel','Export PDF des rapports','Historique des conversations'],
  'Could Have': ['Mode sombre','Application mobile','Intégration Teams'],
  "Won't Have": ['IA générative vocale','Réalité augmentée'],
}

export function NouveauProjet() {
  const user = useAuthStore(s=>s.user)
  const nav = useNavigate()
  const [step, setStep] = useState(1)
  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState(null)

  if (user?.role !== 'pm') {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center card p-10 max-w-sm">
          <div className="w-14 h-14 bg-red-50 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <X size={24} className="text-red-500"/>
          </div>
          <h3 className="font-display font-bold text-navy text-lg mb-2">Accès refusé</h3>
          <p className="text-slate-500 text-sm mb-5">Cette fonctionnalité est réservée aux Project Managers.</p>
          <button onClick={()=>nav('/dashboard')} className="btn-primary w-full">Retour au Dashboard</button>
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
      setProgress(Math.round((s/PIPELINE_STEPS.length)*100))
      if (s >= PIPELINE_STEPS.length) { clearInterval(interval); setTimeout(()=>setStep(3), 600) }
    }, 900)
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Step indicator */}
      <div className="flex items-center gap-3 mb-8">
        {['Upload CDC','Analyse','Résultats'].map((s,i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={clsx('w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold',
              step>i+1 ? 'bg-green-500 text-white' : step===i+1 ? 'bg-navy text-white' : 'bg-slate-200 text-slate-500')}>
              {step>i+1 ? <Check size={13}/> : i+1}
            </div>
            <span className={clsx('text-sm font-medium', step===i+1 ? 'text-navy' : 'text-slate-400')}>{s}</span>
            {i<2 && <ChevronRight size={16} className="text-slate-300 mx-1"/>}
          </div>
        ))}
      </div>

      {step===1 && (
        <div className="card p-8">
          <h2 className="font-display text-xl font-bold text-navy mb-2">Uploader le cahier des charges</h2>
          <p className="text-slate-500 text-sm mb-6">Notre IA va analyser votre CDC et générer un plan de projet complet.</p>
          <div onDrop={(e)=>{e.preventDefault();setDragging(false);const f=e.dataTransfer.files[0];if(f)setFile(f)}}
            onDragOver={(e)=>{e.preventDefault();setDragging(true)}}
            onDragLeave={()=>setDragging(false)}
            className={clsx('border-2 border-dashed rounded-2xl p-12 text-center transition-all',
              dragging ? 'border-cyan bg-cyan/5' : 'border-slate-200 hover:border-slate-300',
              file && 'border-green-400 bg-green-50')}>
            {file ? (
              <>
                <CheckCircle size={36} className="text-green-500 mx-auto mb-3"/>
                <p className="font-medium text-green-700">{file.name}</p>
                <p className="text-xs text-green-500 mt-1">{(file.size/1024).toFixed(0)} KB</p>
              </>
            ) : (
              <>
                <Upload size={36} className="text-slate-300 mx-auto mb-3"/>
                <p className="text-slate-600 font-medium">Déposez votre fichier ici</p>
                <p className="text-xs text-slate-400 mt-1 mb-4">PDF, DOCX · max 10 MB</p>
                <label className="btn-secondary text-sm cursor-pointer">
                  Parcourir
                  <input type="file" accept=".pdf,.docx" className="hidden" onChange={e=>setFile(e.target.files[0])}/>
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

      {step===2 && (
        <div className="card p-8">
          <h2 className="font-display text-xl font-bold text-navy mb-2">Analyse en cours...</h2>
          <p className="text-slate-500 text-sm mb-6">{file?.name}</p>
          <div className="w-full bg-slate-100 rounded-full h-2 mb-6">
            <div className="bg-cyan h-2 rounded-full transition-all duration-700" style={{width:`${progress}%`}}/>
          </div>
          <div className="space-y-3">
            {PIPELINE_STEPS.map((s,i) => (
              <div key={s} className="flex items-center gap-3 p-3 rounded-xl bg-slate-50">
                {i < currentStep ? <CheckCircle size={18} className="text-green-500 shrink-0"/>
                  : i===currentStep ? <Loader size={18} className="text-cyan animate-spin shrink-0"/>
                  : <div className="w-4.5 h-4.5 rounded-full border-2 border-slate-300 shrink-0"/>}
                <span className={clsx('text-sm', i<currentStep ? 'text-slate-700' : i===currentStep ? 'text-navy font-medium' : 'text-slate-400')}>{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {step===3 && (
        <div className="space-y-5 fade-in-up">
          <div className="card p-5">
            <h3 className="font-display font-bold text-navy text-base mb-4">Priorisation MoSCoW</h3>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(MOSCOW).map(([cat, items]) => (
                <div key={cat} className={clsx('p-3 rounded-xl', cat==='Must Have'?'bg-red-50':cat==='Should Have'?'bg-amber-50':cat==='Could Have'?'bg-blue-50':'bg-slate-50')}>
                  <div className="text-xs font-bold mb-2 uppercase tracking-wide text-slate-600">{cat}</div>
                  {items.map(item=><div key={item} className="text-xs text-slate-700 py-0.5">· {item}</div>)}
                </div>
              ))}
            </div>
          </div>
          <div className="card p-5">
            <h3 className="font-display font-bold text-navy text-base mb-4">Allocation recommandée</h3>
            <div className="grid grid-cols-3 gap-3">
              {[['Développeurs',4,'bg-blue-100 text-blue-700'],['Designers',1,'bg-pink-100 text-pink-700'],['DevOps',1,'bg-green-100 text-green-700']].map(([r,n,c])=>(
                <div key={r} className="text-center p-4 bg-slate-50 rounded-xl">
                  <div className={clsx('text-2xl font-display font-bold mb-1',c.split(' ')[1])}>{n}</div>
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

// ─── SETTINGS ───
export function Settings() {
  const user = useAuthStore(s=>s.user)
  return (
    <div className="p-6 max-w-2xl mx-auto space-y-5">
      <div className="card p-5">
        <h3 className="font-display font-bold text-navy mb-4">Profil</h3>
        <div className="flex items-center gap-4 mb-5">
          <div className="w-16 h-16 bg-navy rounded-2xl flex items-center justify-center">
            <span className="text-white text-xl font-bold">{user?.initials}</span>
          </div>
          <div>
            <div className="font-semibold text-slate-800 text-lg">{user?.name}</div>
            <div className="text-slate-500 text-sm">{user?.email}</div>
            <span className={user?.role==='pm'?'badge-pm':'badge-consultant'}>
              {user?.role==='pm'?'Project Manager':'Consultant'}
            </span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="text-xs text-slate-500 block mb-1">Prénom</label><input className="input-field" defaultValue={user?.name?.split(' ')[0]}/></div>
          <div><label className="text-xs text-slate-500 block mb-1">Nom</label><input className="input-field" defaultValue={user?.name?.split(' ')[1]}/></div>
          <div className="col-span-2"><label className="text-xs text-slate-500 block mb-1">Email</label><input className="input-field" defaultValue={user?.email}/></div>
        </div>
        <button className="btn-primary mt-4 text-sm">Sauvegarder</button>
      </div>
      <div className="card p-5">
        <h3 className="font-display font-bold text-navy mb-4">Préférences</h3>
        {[['Notifications email','Recevoir les alertes par email'],['Notifications push','Alertes dans le navigateur'],['Mode compact','Interface plus dense']].map(([label, desc])=>(
          <div key={label} className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0">
            <div><div className="text-sm font-medium text-slate-700">{label}</div><div className="text-xs text-slate-400">{desc}</div></div>
            <label className="relative inline-flex cursor-pointer">
              <input type="checkbox" className="sr-only peer" defaultChecked/>
              <div className="w-10 h-5 bg-slate-200 peer-checked:bg-navy rounded-full transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:w-4 after:h-4 after:bg-white after:rounded-full after:transition-transform peer-checked:after:translate-x-5"/>
            </label>
          </div>
        ))}
      </div>
    </div>
  )
}
