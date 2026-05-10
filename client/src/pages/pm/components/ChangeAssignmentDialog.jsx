// client/src/pages/pm/components/ChangeAssignmentDialog.jsx

import { useState, useMemo } from "react";
import { X, Check, Loader, User, RefreshCw } from "lucide-react";
import clsx from "clsx";
import { changeMatchingAssignment } from "../../../api/pipeline";

const LEVEL_BADGE = {
  excellent: "bg-emerald-100 text-emerald-700 border-emerald-200",
  good:      "bg-green-100   text-green-700   border-green-200",
  medium:    "bg-amber-100   text-amber-700   border-amber-200",
  weak:      "bg-rose-100    text-rose-700    border-rose-200",
};

const LEVEL_BAR = {
  excellent: "bg-emerald-500",
  good:      "bg-green-500",
  medium:    "bg-amber-400",
  weak:      "bg-rose-500",
};

const SENIORITY_BADGE = {
  JUNIOR: "bg-green-100  text-green-700  border-green-200",
  MID:    "bg-blue-100   text-blue-700   border-blue-200",
  SENIOR: "bg-purple-100 text-purple-700 border-purple-200",
};

function round2(n) {
  return Math.round(n * 100) / 100;
}

function barColor(pct) {
  if (pct >= 100) return "bg-rose-500";
  if (pct >= 80)  return "bg-amber-400";
  return "bg-emerald-500";
}

function CapacityQuestion({ label, icon, children }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-base leading-none">{icon}</span>
      <span className="text-[11px] text-slate-500 w-36 shrink-0">{label}</span>
      <div className="flex-1 flex items-center gap-2">{children}</div>
    </div>
  );
}

function SpBar({ pct, value, capacity }) {
  return (
    <>
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={clsx("h-full transition-all", barColor(pct))}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
      <span className="text-[11px] font-semibold text-slate-700 whitespace-nowrap">
        {value}/{capacity} SP
      </span>
    </>
  );
}

export default function ChangeAssignmentDialog({
  open,
  onClose,
  projectId,
  sprintNumber,
  storyId,
  storyTitle,
  requiredProfile,
  currentEmployeeId,
  allocatedSp = 0,
  recommendedTeam = [],
  alternatives = [],
  onResolved,
}) {
  const [selected, setSelected] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const capacityMap = useMemo(() =>
    Object.fromEntries((recommendedTeam ?? []).map((m) => [m.employee_id, m])),
    [recommendedTeam],
  );

  const enrichedAlts = useMemo(() => {
    return alternatives
      .map((opt) => {
        const member      = capacityMap[opt.employee_id];
        const isCurrent   = opt.employee_id === currentEmployeeId;
        const assignedSp  = member?.assigned_sp  ?? 0;
        const capacitySp  = member?.capacity_sp  ?? null;
        const remainingFinal = member?.remaining_capacity_sp ?? opt.remaining_capacity_sp ?? 0;

        const availableForChange = isCurrent
          ? round2(remainingFinal + allocatedSp)
          : remainingFinal;

        // Charge après affectation
        const afterSp  = isCurrent ? assignedSp : round2(assignedSp + allocatedSp);
        const afterPct = capacitySp > 0 ? Math.round((afterSp / capacitySp) * 100) : 0;
        const nowPct   = capacitySp > 0 ? Math.round((assignedSp / capacitySp) * 100) : 0;
        const remainingAfter = capacitySp != null
          ? round2(capacitySp - afterSp)
          : round2(availableForChange - allocatedSp);

        return {
          ...opt,
          assignedSp,
          capacitySp,
          afterSp,
          afterPct,
          nowPct,
          remainingAfter,
          eligible: availableForChange >= allocatedSp,
        };
      })
      .filter((opt) => opt.eligible);
  }, [alternatives, capacityMap, currentEmployeeId, allocatedSp]);

  const sortedAlts = useMemo(() => {
    const arr = [...enrichedAlts];
    arr.sort((a, b) => {
      if (a.employee_id === currentEmployeeId) return -1;
      if (b.employee_id === currentEmployeeId) return 1;
      return (b.skill_score ?? 0) - (a.skill_score ?? 0);
    });
    return arr;
  }, [enrichedAlts, currentEmployeeId]);

  if (!open) return null;

  const handleConfirm = async () => {
    if (selected === null || selected === currentEmployeeId) return;
    setSubmitting(true);
    setError(null);
    try {
      await changeMatchingAssignment(projectId, {
        sprint_number:    sprintNumber,
        story_id:         storyId,
        required_profile: requiredProfile,
        new_employee_id:  selected,
      });
      onResolved?.();
      onClose();
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail ?? "Erreur lors du changement.";
      if (status === 423) {
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
            <p className="text-xs font-semibold text-violet-600 uppercase tracking-wide mb-1 flex items-center gap-1">
              <RefreshCw size={12} /> Changer l&apos;affectation
            </p>
            <h3 className="text-base font-semibold text-slate-800 truncate">{storyTitle}</h3>
            <p className="text-xs text-slate-500 mt-1">
              Sprint <span className="font-semibold">{sprintNumber}</span>
              {" · "}Profil : <span className="font-semibold text-slate-700">{requiredProfile}</span>
              {allocatedSp > 0 && (
                <> · Charge à affecter : <span className="font-semibold text-slate-700">{allocatedSp} SP</span></>
              )}
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

        {sortedAlts.length === 0 && (
          <div className="p-6">
            <p className="text-xs text-slate-500 text-center italic">
              Aucun candidat alternatif disponible pour ce profil sur ce sprint.
            </p>
          </div>
        )}

        {/* Candidats */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {sortedAlts.map((opt) => {
            const isCurrent  = opt.employee_id === currentEmployeeId;
            const isSelected = selected === opt.employee_id;
            const llmFailed  = opt.reason?.includes("indisponible");
            const scorePct   = Math.round((opt.skill_score ?? 0) * 100);
            const scoreBar   = LEVEL_BAR[opt.match_level] ?? "bg-slate-300";

            return (
              <button
                key={opt.employee_id}
                type="button"
                onClick={() => !isCurrent && setSelected(opt.employee_id)}
                disabled={submitting || isCurrent}
                className={clsx(
                  "w-full text-left rounded-xl border-2 p-4 transition-all",
                  isCurrent
                    ? "border-emerald-300 bg-emerald-50/40 cursor-default"
                    : isSelected
                      ? "border-navy bg-navy/5 shadow-sm"
                      : "border-slate-200 hover:border-slate-300 bg-white",
                )}
              >
                <div className="flex items-start gap-3">

                  {/* Avatar */}
                  <div className={clsx(
                    "w-10 h-10 rounded-full flex items-center justify-center shrink-0",
                    isCurrent ? "bg-emerald-500 text-white"
                              : isSelected ? "bg-navy text-white"
                                           : "bg-slate-100 text-slate-500",
                  )}>
                    {isCurrent || isSelected ? <Check size={18} /> : <User size={18} />}
                  </div>

                  <div className="flex-1 min-w-0 space-y-3">

                    {/* Nom + badges */}
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-slate-800 text-sm">{opt.name}</span>
                        <span className={clsx("text-[10px] font-semibold px-1.5 py-0.5 rounded-full border",
                          SENIORITY_BADGE[opt.seniority] ?? "bg-slate-100 text-slate-500 border-slate-200")}>
                          {opt.seniority}
                        </span>
                        <span className={clsx("text-[10px] font-semibold px-1.5 py-0.5 rounded-full border capitalize",
                          LEVEL_BADGE[opt.match_level] ?? "bg-slate-100 text-slate-500 border-slate-200")}>
                          {opt.match_level}
                        </span>
                        {isCurrent && (
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full border bg-emerald-100 text-emerald-700 border-emerald-200">
                            Actuel
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5">{opt.job_title}</p>
                    </div>

                    {/* ── Compatibilité compétences ── */}
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[11px] font-medium text-slate-600">Compatibilité compétences</span>
                        <span className="text-[11px] font-bold text-slate-700">{scorePct}%</span>
                      </div>
                      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className={clsx("h-full", scoreBar)} style={{ width: `${scorePct}%` }} />
                      </div>
                    </div>

                    {/* ── Skills ── */}
                    {llmFailed ? (
                      <p className="text-[11px] text-yellow-700 italic">
                        Compétences non disponibles (évaluation LLM indisponible).
                      </p>
                    ) : (
                      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
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

                    {/* ── Questions capacité ── */}
                    <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2.5 space-y-2">
                      <CapacityQuestion label="Est-il disponible ?" icon="📊">
                        {opt.capacitySp != null ? (
                          <SpBar pct={opt.nowPct} value={opt.assignedSp} capacity={opt.capacitySp} />
                        ) : (
                          <span className="text-[11px] text-emerald-600 font-semibold">
                            Pas encore assigné dans ce sprint
                          </span>
                        )}
                      </CapacityQuestion>

                      <CapacityQuestion label="Sa charge si affecté ?" icon="📥">
                        {opt.capacitySp != null ? (
                          <>
                            <SpBar pct={opt.afterPct} value={opt.afterSp} capacity={opt.capacitySp} />
                            {isCurrent && (
                              <span className="text-[10px] text-slate-400 italic whitespace-nowrap">inchangé</span>
                            )}
                          </>
                        ) : (
                          <span className="text-[11px] font-semibold text-slate-700">
                            {allocatedSp} SP
                          </span>
                        )}
                      </CapacityQuestion>

                      <CapacityQuestion label="Combien reste-t-il ?" icon="🟢">
                        <span className={clsx(
                          "text-[11px] font-semibold",
                          opt.remainingAfter <= 0 ? "text-rose-600"
                            : opt.remainingAfter <= 2 ? "text-amber-600"
                            : "text-emerald-600",
                        )}>
                          {opt.remainingAfter} SP libres
                        </span>
                      </CapacityQuestion>
                    </div>

                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-200 flex items-center justify-between gap-3">
          {error && <p className="text-xs text-red-600 truncate flex-1">{error}</p>}
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
              disabled={selected === null || selected === currentEmployeeId || submitting}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-navy text-white text-xs font-medium hover:bg-navy/90 disabled:opacity-50 transition-colors"
            >
              {submitting ? <Loader size={12} className="animate-spin" /> : <Check size={12} />}
              {submitting ? "Application…" : "Confirmer le changement"}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
