// src/pages/rh/components/SkillsPicker.jsx
// Sélecteur de compétences :
//   - Affiche les compétences existantes (DB) en chips cliquables
//   - Filtre via une barre de recherche
//   - Permet d'ajouter une nouvelle compétence si elle n'est pas dans la liste
//   - Chaque compétence sélectionnée a un niveau (débutant → expert)

import { useState, useMemo } from 'react'
import { Search, Plus, Trash2, Sparkles } from 'lucide-react'

const SKILL_LEVELS = [
  { value: 'beginner',     label: 'Débutant',      color: 'bg-slate-100 text-slate-600' },
  { value: 'intermediate', label: 'Intermédiaire', color: 'bg-sky-100 text-sky-700' },
  { value: 'advanced',     label: 'Avancé',        color: 'bg-blue-100 text-blue-700' },
  { value: 'expert',       label: 'Expert',        color: 'bg-violet-100 text-violet-700' },
]

function levelLabel(v) {
  return SKILL_LEVELS.find(l => l.value === v)?.label || v
}
function levelColor(v) {
  return SKILL_LEVELS.find(l => l.value === v)?.color || 'bg-slate-100 text-slate-600'
}

export default function SkillsPicker({ existingSkills = [], value = [], onChange }) {
  const [search, setSearch] = useState('')
  const [newSkillLevel, setNewSkillLevel] = useState('intermediate')

  // Compétences déjà sélectionnées (noms en lowercase pour comparaison)
  const selectedNames = useMemo(() => new Set(value.map(s => s.name.toLowerCase())), [value])

  // Compétences existantes filtrées par la recherche
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return existingSkills
    return existingSkills.filter(s => s.name.toLowerCase().includes(q))
  }, [existingSkills, search])

  // La recherche ne correspond à aucune skill existante → proposer d'en créer une
  const searchTrimmed = search.trim()
  const isNewSkill = searchTrimmed.length > 0
    && !existingSkills.some(s => s.name.toLowerCase() === searchTrimmed.toLowerCase())

  const toggleExisting = (skill) => {
    const already = selectedNames.has(skill.name.toLowerCase())
    if (already) {
      onChange(value.filter(s => s.name.toLowerCase() !== skill.name.toLowerCase()))
    } else {
      onChange([...value, { name: skill.name, level: 'intermediate' }])
    }
  }

  const addNew = () => {
    if (!searchTrimmed) return
    if (selectedNames.has(searchTrimmed.toLowerCase())) return
    onChange([...value, { name: searchTrimmed, level: newSkillLevel }])
    setSearch('')
  }

  const updateLevel = (idx, level) => {
    const next = [...value]
    next[idx] = { ...next[idx], level }
    onChange(next)
  }

  const remove = (idx) => {
    onChange(value.filter((_, i) => i !== idx))
  }

  return (
    <div className="space-y-3">
      {/* ── Compétences sélectionnées ── */}
      {value.length > 0 && (
        <div className="space-y-2">
          {value.map((s, i) => (
            <div key={i} className="flex items-center gap-2 bg-slate-50 rounded-xl px-3 py-2 border border-slate-100">
              <span className="text-sm font-medium text-slate-700 flex-1 truncate">{s.name}</span>
              <select
                value={s.level}
                onChange={e => updateLevel(i, e.target.value)}
                className="text-xs border-0 bg-transparent outline-none cursor-pointer text-slate-500 pr-1"
              >
                {SKILL_LEVELS.map(l => (
                  <option key={l.value} value={l.value}>{l.label}</option>
                ))}
              </select>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${levelColor(s.level)}`}>
                {levelLabel(s.level)}
              </span>
              <button type="button" onClick={() => remove(i)}
                className="text-slate-300 hover:text-red-400 transition-colors ml-1">
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── Recherche ── */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && isNewSkill) { e.preventDefault(); addNew() } }}
          placeholder="Rechercher une compétence…"
          className="w-full border border-slate-200 rounded-xl pl-8 pr-3 py-2.5 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white"
        />
      </div>

      {/* ── Chips des compétences disponibles ── */}
      <div className="max-h-36 overflow-y-auto">
        {filtered.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {filtered.map(s => {
              const selected = selectedNames.has(s.name.toLowerCase())
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => toggleExisting(s)}
                  className={`text-xs px-3 py-1.5 rounded-full border transition-all font-medium ${
                    selected
                      ? 'bg-cyan/10 border-cyan text-cyan'
                      : 'bg-white border-slate-200 text-slate-600 hover:border-cyan/50 hover:text-cyan'
                  }`}
                >
                  {selected && <span className="mr-1">✓</span>}
                  {s.name}
                </button>
              )
            })}
          </div>
        ) : !isNewSkill ? (
          <p className="text-xs text-slate-400 py-2">Aucune compétence trouvée.</p>
        ) : null}
      </div>

      {/* ── Ajouter une nouvelle compétence ── */}
      {isNewSkill && (
        <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-100 rounded-xl">
          <Sparkles size={14} className="text-amber-500 shrink-0" />
          <span className="text-xs text-amber-700 flex-1">
            "<strong>{searchTrimmed}</strong>" n'existe pas encore.
          </span>
          <select
            value={newSkillLevel}
            onChange={e => setNewSkillLevel(e.target.value)}
            className="text-xs border border-amber-200 bg-white rounded-lg px-2 py-1.5 outline-none text-slate-600"
          >
            {SKILL_LEVELS.map(l => (
              <option key={l.value} value={l.value}>{l.label}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={addNew}
            className="flex items-center gap-1 text-xs bg-amber-500 text-white px-2.5 py-1.5 rounded-lg hover:bg-amber-600 transition-colors font-medium"
          >
            <Plus size={12} /> Ajouter
          </button>
        </div>
      )}
    </div>
  )
}
