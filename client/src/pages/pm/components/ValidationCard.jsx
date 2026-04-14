import { useState } from "react";
import { Zap, ThumbsUp, ThumbsDown, AlertCircle, Loader } from "lucide-react";
import clsx from "clsx";

export default function ValidationCard({ onValidate }) {
  const [feedback,     setFeedback]     = useState("");
  const [showFeedback, setShowFeedback] = useState(false);
  const [submitting,   setSubmitting]   = useState(false);
  const [error,        setError]        = useState(null);

  const handleValidate = async (approved) => {
    if (!approved && !feedback.trim()) { setShowFeedback(true); return; }
    setSubmitting(true);
    setError(null);
    try {
      await onValidate(approved, feedback || null);
      setFeedback("");
      setShowFeedback(false);
    } catch (e) {
      setError(e.response?.data?.detail || "Erreur lors de la validation.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
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
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Ex: Les epics sont trop larges, découpez davantage..."
            rows={3}
            className="w-full text-sm border border-slate-200 rounded-xl px-3 py-2.5
                       focus:outline-none focus:ring-2 focus:ring-amber-200 focus:border-amber-400 resize-none"
          />
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl px-3 py-2 mb-3">
          <AlertCircle size={13} className="shrink-0" /> {error}
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={() => handleValidate(false)}
          disabled={submitting || (showFeedback && !feedback.trim())}
          className={clsx(
            "flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all",
            "border border-red-200 text-red-600 hover:bg-red-50",
            (submitting || (showFeedback && !feedback.trim())) && "opacity-50 cursor-not-allowed",
          )}
        >
          <ThumbsDown size={15} />
          {showFeedback ? "Confirmer le rejet" : "Rejeter"}
        </button>

        <button
          onClick={() => handleValidate(true)}
          disabled={submitting}
          className={clsx(
            "flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all",
            "bg-navy text-white hover:bg-navy/90",
            submitting && "opacity-70 cursor-not-allowed",
          )}
        >
          {submitting ? <Loader size={15} className="animate-spin" /> : <ThumbsUp size={15} />}
          {submitting ? "Envoi..." : "Approuver et continuer"}
        </button>
      </div>
    </div>
  );
}
