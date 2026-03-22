// src/pages/Historique.jsx
import { useState } from 'react'
import { useChatStore } from '../store'
import { useNavigate } from 'react-router-dom'
import { Search, RotateCcw, ChevronRight } from 'lucide-react'
import clsx from 'clsx'

const AGENT_COLORS = {
  RH: 'bg-green-100 text-green-700',
  CRM: 'bg-blue-100 text-blue-700',
  Jira: 'bg-orange-100 text-orange-700',
  Slack: 'bg-purple-100 text-purple-700',
  Calendar: 'bg-cyan-100 text-cyan-700',
}

const FILTERS = ['Tout', 'Cette semaine', 'Ce mois', 'RH', 'CRM', 'Jira', 'Slack', 'Calendar']

export default function Historique() {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('Tout')
  const [expanded, setExpanded] = useState(null)
  const { conversations, setActive } = useChatStore()
  const nav = useNavigate()

  const filtered = conversations.filter(c => {
    const matchSearch = c.title.toLowerCase().includes(search.toLowerCase())
    const matchFilter = filter === 'Tout' || c.agents.includes(filter) ||
      (filter === 'Cette semaine') || (filter === 'Ce mois')
    return matchSearch && matchFilter
  })

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Barre de recherche */}
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-field pl-9" placeholder="Rechercher dans l'historique..."
            value={search} onChange={e => setSearch(e.target.value)} />
        </div>
      </div>

      {/* Filtres */}
      <div className="flex gap-2 mb-5 overflow-x-auto pb-1">
        {FILTERS.map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={clsx('shrink-0 text-xs px-3 py-1.5 rounded-lg font-medium transition-all',
              filter === f ? 'bg-navy text-white' : 'bg-white border border-slate-200 text-slate-600 hover:border-cyan')}>
            {f}
          </button>
        ))}
      </div>

      {/* État vide */}
      {filtered.length === 0 && (
        <div className="text-center py-16">
          <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Search size={22} className="text-slate-400" />
          </div>
          <p className="text-slate-500">Aucune conversation trouvée</p>
        </div>
      )}

      {/* Liste des conversations */}
      <div className="space-y-3">
        {filtered.map(conv => (
          <div key={conv.id} className="card overflow-hidden">
            <div className="p-4 flex items-center gap-4 cursor-pointer hover:bg-slate-50 transition-colors"
              onClick={() => setExpanded(expanded === conv.id ? null : conv.id)}>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-800 text-sm truncate mb-1">{conv.title}</div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400">{conv.date}</span>
                  <span className="text-xs text-slate-400">{conv.messageCount} messages</span>
                  <div className="flex gap-1">
                    {conv.agents.map(a => (
                      <span key={a} className={clsx('text-xs px-1.5 py-0.5 rounded-md font-medium', AGENT_COLORS[a] || 'bg-slate-100 text-slate-600')}>{a}</span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={(e) => { e.stopPropagation(); setActive(conv.id); nav('/chat') }}
                  className="text-xs btn-secondary py-1.5 px-3 flex items-center gap-1">
                  <RotateCcw size={12} /> Reprendre
                </button>
                <ChevronRight size={16} className={clsx('text-slate-400 transition-transform', expanded === conv.id && 'rotate-90')} />
              </div>
            </div>

            {/* Messages expandés */}
            {expanded === conv.id && (
              <div className="border-t border-slate-100 p-4 bg-slate-50 space-y-3">
                {conv.messages.map((msg, i) => (
                  <div key={i} className={clsx('flex gap-2', msg.role === 'user' && 'flex-row-reverse')}>
                    <div className={clsx('text-xs px-3 py-2 rounded-xl max-w-md',
                      msg.role === 'user' ? 'bg-navy text-white' : 'bg-white border border-slate-200 text-slate-700')}>
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