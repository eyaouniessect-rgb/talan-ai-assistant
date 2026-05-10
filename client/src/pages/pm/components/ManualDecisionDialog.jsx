// client/src/pages/pm/components/ManualDecisionDialog.jsx
// Dialog ouvert quand un ProfileAssignment a status="manual_decision_required".
// Le PM choisit un employé parmi les candidate_options (ex aequo après best-fit).

import { useState } from "react";
import { X, Check, Loader, User, AlertCircle, AlertTriangle } from "lucide-react";
import clsx from "clsx";
import { resolveMatchingManualDecision } from "../../../api/pipeline";

const LEVEL_BADGE = {
  excellent: "bg-emerald-100 text-emerald-700 border-emerald-200",
  good:      "bg-green-100   text-green-700   border-green-200",
  medium:    "bg-amber-100   text-amber-700   border-amber-200",
  weak:      "bg-rose-100    text-rose-700    border-rose-200",
};

const SENIORITY_BADGE = {
  JUNIOR: "bg-green-100  text-green-700  border-green-200",
  MID:    "bg-blue-100   text-blue-700   border-blue-200",
  SENIOR: "bg-purple-100 text-purple-700 border-purple-200",
};

export default function ManualDecisionDialog({
  open,
  onClose,
  projectId,
  sprintNumber,
  storyId,
  storyTitle,
  requiredProfile,
  candidateOptions = [],
  onResolved,
}) {
  const [selected, setSelected] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!open) return null;

  const handleConfirm = async () => {
    if (selected === null) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await resolveMatchingManualDecision(projectId, {
        sprint_number:    sprintNumber,
        story_id:         storyId,
        required_profile: requiredProfile,
        employee_id:      selected,
      });
      onResolved?.();
      onClose();
      // Si déjà résolue (réponse idempotente), rafraîchir sans message d'erreur.
      if (res?.already_resolved) onResolved?.();
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail ?? "Erreur lors de la résolution.";
      // 423 = recalcul en cours ; 400 avec "statut" = déjà résolue → rafraîchir
      if (status === 423 || (status === 400 && detail.includes("statut"))) {
        onResolved?.();
        onClose();
      } else {
        setError(detail);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col border border-slate-200">

        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-200 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-amber-600 uppercase tracking-wide mb-1">
              Décision manuelle requise
            </p>
            <h3 className="text-base font-semibold text-slate-800 truncate">
              {storyTitle}
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Sprint <span className="font-semibold">{sprintNumber}</span> · Profil requis :{" "}
              <span className="font-semibold text-slate-700">{requiredProfile}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="p-1 rounded-lg hover:bg-slate-100 transition-colors text-slate-500 disabled:opacity-50"
          >
            <X size={18} />
          </button>
        </div>

        {/* Explication */}
        <div className="px-5 py-3 bg-amber-50 border-b border-amber-200">
          <div className="flex items-start gap-2">
            <AlertCircle size={14} className="text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 leading-relaxed">
              Plusieurs candidats sont strictement équivalents (même match, même waste, même score, même proximité de séniorité).
              Choisis le collaborateur à affecter pour ce profil.
            </p>
          </div>
        </div>

        {/* Avertissement si le scoring LLM a échoué pour tous les candidats */}
        {candidateOptions.length > 0 &&
          candidateOptions.every((o) => o.reason?.includes("indisponible")) && (
          <div className="px-5 py-2.5 bg-yellow-50 border-b border-yellow-200 flex items-start gap-2">
            <AlertTriangle size={13} className="text-yellow-600 shrink-0 mt-0.5" />
            <p className="text-xs text-yellow-800">
              Le scoring LLM n&apos;a pas pu être calculé pour ces candidats.
              Les scores affichés sont des estimations par défaut (50 %).
              Les compétences maîtrisées / manquantes ne sont pas disponibles.
            </p>
          </div>
        )}

        {/* Liste des options */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {candidateOptions.map((opt) => {
            const isSelected    = selected === opt.employee_id;
            const llmFailed     = opt.reason?.includes("indisponible");
            const scorePct      = Math.round((opt.skill_score ?? 0) * 100);
            return (
              <button
                key={opt.employee_id}
                type="button"
                onClick={() => setSelected(opt.employee_id)}
                disabled={submitting}
                className={clsx(
                  "w-full text-left rounded-xl border-2 p-4 transition-all",
                  isSelected
                    ? "border-navy bg-navy/5 shadow-sm"
                    : "border-slate-200 hover:border-slate-300 bg-white",
                )}
              >
                <div className="flex items-start gap-3">
                  <div className={clsx(
                    "w-10 h-10 rounded-full flex items-center justify-center shrink-0",
                    isSelected ? "bg-navy text-white" : "bg-slate-100 text-slate-500",
                  )}>
                    {isSelected ? <Check size={18} /> : <User size={18} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-slate-800 text-sm">{opt.name}</span>
                      <span className={clsx(
                        "text-[10px] font-semibold px-1.5 py-0.5 rounded-full border",
                        SENIORITY_BADGE[opt.seniority] ?? "bg-slate-100 text-slate-500 border-slate-200",
                      )}>
                        {opt.seniority}
                      </span>
                      <span className={clsx(
                        "text-[10px] font-semibold px-1.5 py-0.5 rounded-full border capitalize",
                        LEVEL_BADGE[opt.match_level] ?? "bg-slate-100 text-slate-500 border-slate-200",
                      )}>
                        {opt.match_level}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">{opt.job_title}</p>

                    {/* Score barre */}
                    <div className="mt-2 flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-emerald-500"
                          style={{ width: `${scorePct}%` }}
                        />
                      </div>
                      <span className="text-xs font-semibold text-slate-600 w-10 text-right">
                        {scorePct}%
                      </span>
                    </div>

                    {/* Détails skills */}
                    {llmFailed ? (
                      <p className="mt-2 text-[11px] text-yellow-700 italic">
                        Compétences non disponibles (évaluation LLM indisponible).
                      </p>
                    ) : (
                      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
                        <div>
                          <span className="text-emerald-600 font-medium">Maîtrisées : </span>
                          <span className="text-slate-600">
                            {opt.matched_skills?.length ? opt.matched_skills.join(", ") : "—"}
                          </span>
                        </div>
                        <div>
                          <span className="text-blue-600 font-medium">Inférées : </span>
                          <span className="text-slate-600">
                            {opt.inferred_matches?.length ? opt.inferred_matches.join(", ") : "—"}
                          </span>
                        </div>
                        <div className="col-span-2">
                          <span className="text-rose-600 font-medium">Manquantes : </span>
                          <span className="text-slate-600">
                            {opt.missing_skills?.length ? opt.missing_skills.join(", ") : "—"}
                          </span>
                        </div>
                      </div>
                    )}

                    <div className="mt-2 flex items-center gap-3 text-[11px] text-slate-500">
                      <span>Capa restante : <strong>{opt.remaining_capacity_sp} SP</strong></span>
                      <span>Waste : <strong>{opt.waste} SP</strong></span>
                    </div>

                    {opt.reason && (
                      <p className="mt-2 text-[11px] text-slate-500 italic">
                        « {opt.reason} »
                      </p>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-200 flex items-center justify-between gap-3">
          {error && (
            <p className="text-xs text-red-600 truncate flex-1">{error}</p>
          )}
          <div className="flex items-center gap-2 ml-auto">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
            >
              Annuler
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={selected === null || submitting}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-navy text-white text-xs font-medium hover:bg-navy/90 disabled:opacity-50 transition-colors"
            >
              {submitting ? <Loader size={12} className="animate-spin" /> : <Check size={12} />}
              {submitting ? "Application…" : "Confirmer la sélection"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
