// src/pages/rh/components/ContactModal.jsx
import { useState } from 'react'
import { X, Send, Loader, Plus, Trash2 } from 'lucide-react'
import { contactEmployeeApi } from '../../../api/rh'

export default function ContactModal({ employee, onClose }) {
  const [subject, setSubject]   = useState(`Objet : [à compléter] — ${employee.name}`)
  const [body, setBody]         = useState(
`Bonjour ${employee.name.split(' ')[0]},

[Corps du message]

Cordialement,
L'équipe RH — Talan Tunisie`
  )
  const [ccEmails, setCcEmails] = useState([''])
  const [loading, setLoading]   = useState(false)
  const [success, setSuccess]   = useState(false)
  const [error, setError]       = useState('')

  const addCc    = () => setCcEmails(c => [...c, ''])
  const removeCc = (i) => setCcEmails(c => c.filter((_, idx) => idx !== i))
  const setCc    = (i, val) => setCcEmails(c => c.map((v, idx) => idx === i ? val : v))

  const handleSend = async () => {
    setLoading(true)
    setError('')
    try {
      const cc = ccEmails.filter(e => e.trim() !== '')
      await contactEmployeeApi(employee.id, { subject, body, cc_emails: cc })
      setSuccess(true)
    } catch (e) {
      setError(e.response?.data?.detail || "Erreur lors de l'envoi")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 shrink-0">
          <div>
            <div className="font-bold text-navy text-sm">Contacter l'employé</div>
            <div className="text-xs text-slate-400 mt-0.5">{employee.name} — {employee.email}</div>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors">
            <X size={16} className="text-slate-400" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4 overflow-y-auto flex-1">
          {/* Destinataire (readonly) */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">À</label>
            <div className="border border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-slate-50 text-slate-600">
              {employee.email}
            </div>
          </div>

          {/* CC */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-medium text-slate-500">CC</label>
              <button
                onClick={addCc}
                className="text-xs text-cyan hover:text-cyan/80 flex items-center gap-1 transition-colors"
              >
                <Plus size={11} /> Ajouter
              </button>
            </div>
            <div className="space-y-2">
              {ccEmails.map((cc, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type="email"
                    value={cc}
                    onChange={e => setCc(i, e.target.value)}
                    placeholder="email@talan.com"
                    className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan"
                  />
                  <button
                    onClick={() => removeCc(i)}
                    className="p-1.5 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <Trash2 size={13} className="text-slate-300 hover:text-red-400" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Objet */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">Objet</label>
            <input
              type="text"
              value={subject}
              onChange={e => setSubject(e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan"
            />
          </div>

          {/* Corps */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">Corps du message</label>
            <textarea
              value={body}
              onChange={e => setBody(e.target.value)}
              rows={8}
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan resize-none font-mono"
            />
          </div>

          {error && (
            <div className="text-xs text-red-500 bg-red-50 border border-red-100 rounded-xl px-3 py-2">
              {error}
            </div>
          )}
          {success && (
            <div className="text-xs text-green-600 bg-green-50 border border-green-100 rounded-xl px-3 py-2">
              ✅ Email envoyé avec succès à {employee.email} !
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-2 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-500 hover:bg-slate-50 rounded-xl transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={handleSend}
            disabled={loading || success}
            className="px-4 py-2 text-sm bg-cyan text-white rounded-xl hover:bg-cyan/90 transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {loading ? <Loader size={13} className="animate-spin" /> : <Send size={13} />}
            Envoyer
          </button>
        </div>
      </div>
    </div>
  )
}
