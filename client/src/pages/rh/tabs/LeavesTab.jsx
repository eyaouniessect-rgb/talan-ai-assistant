// src/pages/rh/tabs/LeavesTab.jsx
import { useState, useEffect } from 'react'
import { CheckCircle, XCircle, RefreshCw, Filter, FileText, ExternalLink } from 'lucide-react'
import { getLeavesApi, approveLeaveApi, rejectLeaveApi } from '../../../api/rh'
import clsx from 'clsx'

// ── Helpers ─────────────────────────────────────────────

const LEAVE_TYPE_LABEL = {
  annual:      'Annuel',
  maternity:   'Maternité',
  paternity:   'Paternité',
  bereavement: 'Décès',
  unpaid:      'Sans solde',
  sick:        'Maladie',
  other:       'Autre',
}

const STATUS_STYLE = {
  pending:   { label: 'En attente',  cls: 'bg-amber-100 text-amber-700'   },
  approved:  { label: 'Approuvé',    cls: 'bg-green-100 text-green-700'   },
  rejected:  { label: 'Rejeté',      cls: 'bg-red-100 text-red-600'       },
  cancelled: { label: 'Annulé',      cls: 'bg-slate-100 text-slate-500'   },
}

const LEAVE_TYPE_COLOR = {
  annual:      'bg-blue-50 text-blue-700',
  maternity:   'bg-pink-50 text-pink-700',
  paternity:   'bg-sky-50 text-sky-700',
  bereavement: 'bg-slate-100 text-slate-600',
  unpaid:      'bg-orange-50 text-orange-700',
  sick:        'bg-red-50 text-red-600',
  other:       'bg-gray-100 text-gray-600',
}

const FILTERS = [
  { value: '',          label: 'Tous'         },
  { value: 'pending',   label: 'En attente'   },
  { value: 'approved',  label: 'Approuvés'    },
  { value: 'rejected',  label: 'Rejetés'      },
]

// ── Reject modal ─────────────────────────────────────────

function RejectModal({ leave, onConfirm, onCancel }) {
  const [reason, setReason] = useState('')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6 space-y-4">
        <h3 className="font-semibold text-slate-800 text-sm">Rejeter la demande de {leave.employee_name}</h3>
        <textarea
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Raison du rejet (optionnel)…"
          rows={3}
          className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm resize-none focus:border-red-400 focus:ring-2 focus:ring-red-100 outline-none"
        />
        <div className="flex gap-3">
          <button onClick={onCancel}
            className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm text-slate-600 hover:bg-slate-50 transition-colors">
            Annuler
          </button>
          <button onClick={() => onConfirm(reason)}
            className="flex-1 py-2.5 bg-red-500 text-white rounded-xl text-sm font-medium hover:bg-red-600 transition-colors">
            Confirmer le rejet
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────

export default function LeavesTab() {
  const [leaves, setLeaves]         = useState([])
  const [loading, setLoading]       = useState(true)
  const [filter, setFilter]         = useState('pending')
  const [actionId, setActionId]     = useState(null)   // ID en cours de traitement
  const [rejectTarget, setRejectTarget] = useState(null)

  const load = async (f = filter) => {
    setLoading(true)
    try {
      setLeaves(await getLeavesApi(f || null))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filter])

  const handleApprove = async (lv) => {
    setActionId(lv.id)
    try {
      await approveLeaveApi(lv.id)
      setLeaves(prev => prev.map(l => l.id === lv.id ? { ...l, status: 'approved' } : l))
    } finally {
      setActionId(null)
    }
  }

  const handleReject = async (reason) => {
    const lv = rejectTarget
    setRejectTarget(null)
    setActionId(lv.id)
    try {
      await rejectLeaveApi(lv.id, reason)
      setLeaves(prev => prev.map(l => l.id === lv.id ? { ...l, status: 'rejected' } : l))
    } finally {
      setActionId(null)
    }
  }

  const pending = leaves.filter(l => l.status === 'pending').length

  return (
    <div className="p-6 space-y-5 max-w-6xl mx-auto">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-xl p-1">
          {FILTERS.map(f => (
            <button key={f.value}
              onClick={() => setFilter(f.value)}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                filter === f.value
                  ? 'bg-navy text-white'
                  : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50',
              )}
            >
              {f.label}
              {f.value === 'pending' && pending > 0 && filter !== 'pending' && (
                <span className="ml-1.5 bg-amber-400 text-white text-[10px] px-1.5 py-0.5 rounded-full">{pending}</span>
              )}
            </button>
          ))}
        </div>
        <button onClick={() => load()}
          className="p-2.5 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors text-slate-500 ml-auto">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Stats rapides */}
      {filter === '' && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {['pending', 'approved', 'rejected', 'cancelled'].map(s => {
            const count = leaves.filter(l => l.status === s).length
            const st = STATUS_STYLE[s]
            return (
              <div key={s} className="bg-white border border-slate-100 rounded-2xl p-4 shadow-sm">
                <div className={`text-xs font-medium px-2 py-0.5 rounded-full inline-block mb-2 ${st.cls}`}>{st.label}</div>
                <div className="text-2xl font-bold text-navy">{count}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* Table */}
      <div className="bg-white border border-slate-100 rounded-2xl overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr>
              {['Employé', 'Type', 'Période', 'Jours', 'Statut', 'Justificatif', 'Actions'].map(h => (
                <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {loading ? (
              <tr><td colSpan={7} className="text-center py-12 text-slate-400 text-sm">Chargement…</td></tr>
            ) : leaves.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-12">
                  <FileText size={32} className="text-slate-200 mx-auto mb-2" />
                  <p className="text-slate-400 text-sm">Aucune demande</p>
                </td>
              </tr>
            ) : leaves.map(lv => {
              const st = STATUS_STYLE[lv.status] || STATUS_STYLE.other
              const isPending = lv.status === 'pending'
              const isBusy = actionId === lv.id
              return (
                <tr key={lv.id} className="hover:bg-slate-50/60 transition-colors">
                  {/* Employé */}
                  <td className="px-4 py-3.5">
                    <div className="font-medium text-slate-800">{lv.employee_name}</div>
                    <div className="text-xs text-slate-400">{lv.team || lv.employee_email}</div>
                  </td>
                  {/* Type */}
                  <td className="px-4 py-3.5">
                    <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${LEAVE_TYPE_COLOR[lv.leave_type] || 'bg-slate-100 text-slate-600'}`}>
                      {LEAVE_TYPE_LABEL[lv.leave_type] || lv.leave_type}
                    </span>
                  </td>
                  {/* Période */}
                  <td className="px-4 py-3.5 text-slate-600 whitespace-nowrap">
                    {new Date(lv.start_date).toLocaleDateString('fr-FR')}
                    <span className="text-slate-300 mx-1">→</span>
                    {new Date(lv.end_date).toLocaleDateString('fr-FR')}
                  </td>
                  {/* Jours */}
                  <td className="px-4 py-3.5 text-center font-semibold text-slate-700">
                    {lv.days_count ?? '—'}
                  </td>
                  {/* Statut */}
                  <td className="px-4 py-3.5">
                    <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${st.cls}`}>{st.label}</span>
                  </td>
                  {/* Justificatif */}
                  <td className="px-4 py-3.5">
                    {lv.justification_url ? (
                      <a href={lv.justification_url} target="_blank" rel="noopener noreferrer"
                        className="flex items-center gap-1 text-xs text-cyan hover:underline">
                        <ExternalLink size={12} /> Voir
                      </a>
                    ) : (
                      <span className="text-slate-300 text-xs">—</span>
                    )}
                  </td>
                  {/* Actions */}
                  <td className="px-4 py-3.5">
                    {isPending ? (
                      <div className="flex items-center gap-2">
                        <button
                          disabled={isBusy}
                          onClick={() => handleApprove(lv)}
                          className="flex items-center gap-1 px-3 py-1.5 bg-green-50 hover:bg-green-100 text-green-700 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                        >
                          <CheckCircle size={13} />
                          Approuver
                        </button>
                        <button
                          disabled={isBusy}
                          onClick={() => setRejectTarget(lv)}
                          className="flex items-center gap-1 px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                        >
                          <XCircle size={13} />
                          Rejeter
                        </button>
                      </div>
                    ) : (
                      <span className="text-slate-300 text-xs">—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {rejectTarget && (
        <RejectModal
          leave={rejectTarget}
          onConfirm={handleReject}
          onCancel={() => setRejectTarget(null)}
        />
      )}
    </div>
  )
}
