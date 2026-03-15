import { useAuthStore } from '../store'
import { PROJECTS, TICKETS, TEAM_MEMBERS, ACTIVITY } from '../data/mock'
import { TrendingUp, Clock, AlertCircle, MessageSquare, Upload, CheckCircle, Circle, ArrowRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import clsx from 'clsx'

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

function PMDashboard() {
  const nav = useNavigate()
  return (
    <div className="p-6 space-y-6">
      {/* Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard icon={TrendingUp} label="Projets gérés" value="5" color="bg-blue-50 text-blue-600"/>
        <MetricCard icon={CheckCircle} label="Membres d'équipe" value="12" color="bg-purple-50 text-purple-600"/>
        <MetricCard icon={AlertCircle} label="Tickets en cours" value="23" color="bg-amber-50 text-amber-600"/>
        <MetricCard icon={Circle} label="Disponibilité équipe" value="85%" color="bg-green-50 text-green-600" sub="10/12 membres"/>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Team */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display font-bold text-navy text-base">Vue d'ensemble équipe</h3>
            <span className="text-xs text-slate-400">{TEAM_MEMBERS.length} membres</span>
          </div>
          <div className="space-y-2">
            {TEAM_MEMBERS.map(m => (
              <div key={m.id} className="flex items-center gap-3 p-2.5 hover:bg-slate-50 rounded-xl transition-colors">
                <div className="w-8 h-8 bg-navy/10 rounded-lg flex items-center justify-center shrink-0">
                  <span className="text-navy text-xs font-bold">{m.initials}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-slate-800 truncate">{m.name}</div>
                  <div className="text-xs text-slate-400 truncate">{m.project}</div>
                </div>
                <div className={clsx('w-2 h-2 rounded-full shrink-0', m.available ? 'bg-green-400' : 'bg-red-400')}/>
              </div>
            ))}
          </div>
        </div>

        {/* Projects Kanban */}
        <div className="card p-5">
          <h3 className="font-display font-bold text-navy text-base mb-4">Projets en cours</h3>
          <div className="grid grid-cols-3 gap-3">
            {['À faire','En cours','Terminé'].map(col => (
              <div key={col}>
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{col}</div>
                {PROJECTS.filter(p =>
                  col==='À faire' ? p.status==='En attente' :
                  col==='En cours' ? p.status==='En cours' : p.status==='Terminé'
                ).map(p => (
                  <div key={p.id} className="bg-slate-50 rounded-lg p-2.5 mb-2 border-l-2 border-cyan">
                    <div className="text-xs font-medium text-slate-700 truncate">{p.name}</div>
                    <div className="text-xs text-slate-400 truncate">{p.client}</div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CDC Upload */}
      <div className="card p-5">
        <h3 className="font-display font-bold text-navy text-base mb-4">Analyser un nouveau projet</h3>
        <div onClick={()=>nav('/nouveau-projet')}
          className="border-2 border-dashed border-slate-200 hover:border-cyan rounded-2xl p-8 text-center cursor-pointer transition-all hover:bg-cyan/5 group">
          <div className="w-12 h-12 bg-slate-100 group-hover:bg-cyan/10 rounded-xl flex items-center justify-center mx-auto mb-3 transition-colors">
            <Upload size={22} className="text-slate-400 group-hover:text-cyan transition-colors"/>
          </div>
          <p className="text-sm font-medium text-slate-600 group-hover:text-navy">Déposer votre cahier des charges ici</p>
          <p className="text-xs text-slate-400 mt-1">PDF, DOCX · ou cliquez pour analyser</p>
        </div>
      </div>
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
