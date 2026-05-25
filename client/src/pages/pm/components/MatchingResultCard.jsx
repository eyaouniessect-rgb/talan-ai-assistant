// client/src/pages/pm/components/MatchingResultCard.jsx
// Affiche le résultat complet du Step 5 — Matching :
//   - résumé global (compteurs sprint_status, warning, missing)
//   - liste de sprints (cards expansibles)
//        > équipe recommandée du sprint (membres, capacités)
//        > stories du sprint :
//             > badges status story
//             > pour chaque profil requis : assigné OU issue
//             > "Pourquoi ?" → drawer explainability avec matched/inferred/missing/reason

import { useState, useMemo, useEffect, useCallback } from "react";
import {
  ChevronDown, ChevronRight, User, Users, AlertCircle, AlertTriangle,
  CheckCircle, XCircle, Info, Sparkles, X, Eye, ArrowDownCircle,
  Mail, Briefcase, RefreshCw, Play, Lock, Flag,
} from "lucide-react";
import clsx from "clsx";
import RecruitmentRequestDialog from "./RecruitmentRequestDialog";
import ChangeAssignmentDialog from "./ChangeAssignmentDialog";
import {
  rerunMatching,
  getProjectSprints,
  startSprint,
  closeSprint,
} from "../../../api/pipeline";


// ─────────────────────────────────────────────────────────────
// Lifecycle DB status (planned / active / completed)
// ─────────────────────────────────────────────────────────────

const LIFECYCLE_BADGE = {
  planned:   { label: "Planifié", cls: "bg-slate-100   text-slate-600   border-slate-200" },
  active:    { label: "En cours", cls: "bg-blue-100    text-blue-700    border-blue-200" },
  completed: { label: "Terminé",  cls: "bg-emerald-100 text-emerald-700 border-emerald-200" },
};


function SprintLifecycleControls({ dbSprint, allDbSprints, projectId, sprintNumber, onChange }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [earlyStartModal, setEarlyStartModal] = useState(null); // { message } or null

  if (!dbSprint) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-500 italic">
        Sprint pas encore matérialisé en base — validez la phase staffing pour activer le cycle de vie.
      </div>
    );
  }

  const status = dbSprint.status;
  const otherActive = allDbSprints.find(
    (s) => s.status === "active" && s.sprint_number !== sprintNumber,
  );
  const prevSprint  = sprintNumber > 1
    ? allDbSprints.find((s) => s.sprint_number === sprintNumber - 1)
    : null;
  const prevNotDone = sprintNumber > 1 && (!prevSprint || prevSprint.status !== "completed");

  const canStart = status === "planned" && !otherActive && !prevNotDone;
  const canClose = status === "active";

  const startTooltip = !canStart
    ? status !== "planned"
      ? `Sprint déjà ${LIFECYCLE_BADGE[status]?.label?.toLowerCase() ?? status}`
      : otherActive
        ? `Sprint ${otherActive.sprint_number} est déjà actif — clôturez-le d'abord`
        : `Sprint précédent (${sprintNumber - 1}) doit être clôturé`
    : "Démarrer ce sprint";

  const doStart = useCallback(async (force) => {
    setBusy(true); setError(null);
    try {
      const res = await startSprint(projectId, sprintNumber, force);
      if (res?.requires_confirmation) {
        setEarlyStartModal({ message: res.message });
        setBusy(false);
        return;
      }
      setEarlyStartModal(null);
      onChange?.();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Échec du démarrage du sprint.");
    } finally {
      setBusy(false);
    }
  }, [projectId, sprintNumber, onChange]);

  const doClose = useCallback(async () => {
    if (!window.confirm(`Clôturer le sprint ${sprintNumber} ? Cette action est définitive.`)) return;
    setBusy(true); setError(null);
    try {
      await closeSprint(projectId, sprintNumber);
      onChange?.();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Échec de la clôture du sprint.");
    } finally {
      setBusy(false);
    }
  }, [projectId, sprintNumber, onChange]);

  const cfg = LIFECYCLE_BADGE[status] ?? LIFECYCLE_BADGE.planned;

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-slate-600">Cycle de vie :</span>
          <span className={clsx(
            "text-[10px] font-semibold px-2 py-0.5 rounded-full border",
            cfg.cls,
          )}>
            {cfg.label}
          </span>
          {dbSprint.actual_start_date && (
            <span className="text-[10px] text-slate-500">
              démarré le {dbSprint.actual_start_date}
            </span>
          )}
          {dbSprint.actual_end_date && (
            <span className="text-[10px] text-slate-500">
              clôturé le {dbSprint.actual_end_date}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {canStart && (
            <button
              type="button"
              onClick={() => doStart(false)}
              disabled={busy}
              title={startTooltip}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
            >
              <Play size={11} /> {busy ? "Démarrage…" : "Démarrer le sprint"}
            </button>
          )}
          {!canStart && status === "planned" && (
            <span
              title={startTooltip}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed"
            >
              <Lock size={11} /> Démarrage bloqué
            </span>
          )}
          {canClose && (
            <button
              type="button"
              onClick={doClose}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50"
            >
              <Flag size={11} /> {busy ? "Clôture…" : "Clôturer le sprint"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p className="mt-2 text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded px-2 py-1">
          {error}
        </p>
      )}

      {earlyStartModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle size={20} className="text-amber-500 shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="text-sm font-bold text-slate-800 mb-1">
                  Démarrage anticipé du sprint
                </h3>
                <p className="text-xs text-slate-600">{earlyStartModal.message}</p>
              </div>
            </div>
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setEarlyStartModal(null)}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              >
                Non
              </button>
              <button
                type="button"
                onClick={() => doStart(true)}
                disabled={busy}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                Démarrer comme même
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Helpers visuels
// ─────────────────────────────────────────────────────────────

const SPRINT_STATUS_BADGE = {
  fully_staffed:            { label: "Sprint complet",       cls: "bg-emerald-100 text-emerald-700 border-emerald-200", Icon: CheckCircle },
  partially_staffed:        { label: "Partiellement staffé", cls: "bg-amber-100   text-amber-700   border-amber-200",   Icon: AlertTriangle },
  not_staffed:              { label: "Non staffé",           cls: "bg-rose-100    text-rose-700    border-rose-200",    Icon: XCircle },
};

const STORY_STATUS_BADGE = {
  fully_assigned:           { label: "Affectée",         cls: "bg-emerald-100 text-emerald-700 border-emerald-200", Icon: CheckCircle },
  partially_assigned:       { label: "Partielle",        cls: "bg-amber-100   text-amber-700   border-amber-200",   Icon: AlertTriangle },
  not_assigned:             { label: "Non affectée",     cls: "bg-rose-100    text-rose-700    border-rose-200",    Icon: XCircle },
};

const PROFILE_STATUS_LABEL = {
  assigned:                 { label: "Affecté",                cls: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  assigned_with_warning:    { label: "Affecté (avec alerte)",  cls: "bg-amber-100   text-amber-700   border-amber-200" },
  missing_profile:          { label: "À recruter",             cls: "bg-rose-100    text-rose-700    border-rose-200" },
  capacity_gap:             { label: "Capacité insuffisante",  cls: "bg-orange-100  text-orange-700  border-orange-200" },
  no_available_candidate:   { label: "Aucun candidat",         cls: "bg-rose-100    text-rose-700    border-rose-200" },
};

const MATCH_LEVEL_BADGE = {
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


function StatusBadge({ map, status }) {
  const cfg = map[status] ?? { label: status, cls: "bg-slate-100 text-slate-500 border-slate-200", Icon: Info };
  const Icon = cfg.Icon ?? Info;
  return (
    <span className={clsx(
      "inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full border whitespace-nowrap",
      cfg.cls,
    )}>
      <Icon size={10} />
      {cfg.label}
    </span>
  );
}


// ─────────────────────────────────────────────────────────────
// Drawer "Pourquoi ce candidat ?" (explainability)
// ─────────────────────────────────────────────────────────────

function ExplainabilityDrawer({ open, onClose, assignment, storyTitle, requiredProfile, requiredSkills }) {
  if (!open || !assignment) return null;

  const score    = assignment.skill_score;
  const scorePct = score == null ? null : Math.round(score * 100);
  const matched  = assignment.matched_skills   ?? [];
  const inferred = assignment.inferred_matches ?? [];
  const missing  = assignment.missing_skills   ?? [];

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30">
      <div className="bg-white w-full max-w-md h-full overflow-y-auto shadow-2xl border-l border-slate-200">

        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-200 sticky top-0 bg-white z-10 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-violet-600 mb-1 flex items-center gap-1">
              <Sparkles size={10} /> Explainability
            </p>
            <h3 className="text-sm font-semibold text-slate-800 truncate">
              Pourquoi {assignment.employee_name} ?
            </h3>
            <p className="text-xs text-slate-500 mt-0.5 truncate">
              {requiredProfile} · {storyTitle}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-100 text-slate-500"
          >
            <X size={16} />
          </button>
        </div>

        {/* Score global */}
        {scorePct != null && (
          <div className="p-5 border-b border-slate-200">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-700">Score de compétences</span>
              <span className={clsx(
                "text-[10px] font-bold px-1.5 py-0.5 rounded-full border capitalize",
                MATCH_LEVEL_BADGE[assignment.match_level] ?? "bg-slate-100 text-slate-500 border-slate-200",
              )}>
                {assignment.match_level}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500" style={{ width: `${scorePct}%` }} />
              </div>
              <span className="text-base font-bold text-slate-800 w-12 text-right">
                {scorePct}%
              </span>
            </div>
            <p className="text-[10px] text-slate-500 mt-2">
              Calcul : (compétences maîtrisées + déduites) / compétences requises de la story.
            </p>
          </div>
        )}

        {/* Compétences maîtrisées */}
        <SkillSection
          title="Compétences maîtrisées"
          subtitle="Présentes directement dans le profil du collaborateur."
          color="emerald"
          skills={matched}
        />

        {/* Compétences inférées */}
        <SkillSection
          title="Compétences inférées"
          subtitle="Déduites grâce à une compétence proche (ex : React JS → JavaScript)."
          color="blue"
          skills={inferred}
        />

        {/* Compétences manquantes */}
        <SkillSection
          title="Compétences manquantes"
          subtitle="Compétences requises pour la story et absentes du profil."
          color="rose"
          skills={missing}
        />

        {/* Récap couverture (scopé au profil) */}
        <div className="px-5 py-4 border-b border-slate-200 bg-slate-50 space-y-1">
          {(matched.length + inferred.length + missing.length) > 0 ? (
            <p className="text-[11px] text-slate-600">
              Couverture pour ce profil :{" "}
              <strong>
                {matched.length + inferred.length}/{matched.length + inferred.length + missing.length}
              </strong>{" "}
              compétences relevant de ce profil trouvées.
            </p>
          ) : (
            <p className="text-[11px] text-slate-500 italic">
              Aucune compétence relevant de ce profil dans cette story.
            </p>
          )}
          {requiredSkills?.length > 0 && (
            <p className="text-[10px] text-slate-400">
              Story totale : {requiredSkills.length} compétences requises pour l&apos;ensemble des
              profils. Le score se calcule uniquement sur les compétences scopées au profil scoré
              — un Backend n&apos;est jamais pénalisé pour les skills d&apos;un Frontend.
            </p>
          )}
        </div>

        {/* Note "Compétences hors scope" pour transparence */}
        {requiredSkills?.length > matched.length + inferred.length + missing.length && (
          <div className="px-5 py-3 border-b border-slate-200">
            <p className="text-[11px] font-semibold text-slate-700 mb-1.5 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-slate-400" />
              Hors scope (autres profils)
              <span className="ml-auto text-[10px] font-normal text-slate-400">
                {requiredSkills.length - (matched.length + inferred.length + missing.length)}
              </span>
            </p>
            <p className="text-[10px] text-slate-500 mb-2">
              Compétences requises par la story mais relevant d&apos;un autre profil
              (Frontend/AI/etc.). Non comptabilisées dans le score de ce candidat.
            </p>
            <div className="flex flex-wrap gap-1">
              {requiredSkills
                .filter((s) => ![...matched, ...inferred, ...missing].includes(s))
                .map((s) => (
                  <span
                    key={s}
                    className="text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-slate-50 text-slate-500 border-slate-200"
                  >
                    {s}
                  </span>
                ))}
            </div>
          </div>
        )}

        {/* Reason texte LLM */}
        {assignment.reason && (
          <div className="p-5 border-b border-slate-200">
            <p className="text-[11px] font-semibold text-slate-700 mb-1.5 flex items-center gap-1">
              <Info size={11} /> Justification IA
            </p>
            <p className="text-xs text-slate-600 italic leading-relaxed">
              « {assignment.reason} »
            </p>
          </div>
        )}

        {/* Warning si applicable */}
        {assignment.warning_type && (
          <div className="m-5 rounded-lg border border-amber-200 bg-amber-50 p-3">
            <p className="text-[11px] font-semibold text-amber-700 mb-1 flex items-center gap-1">
              <AlertTriangle size={11} />
              {assignment.warning_type === "medium_skill_match"
                ? "Compatibilité moyenne"
                : "Compatibilité faible"}
            </p>
            <p className="text-[11px] text-amber-700">
              Le PM peut envisager un accompagnement ou rechercher un profil mieux adapté.
            </p>
          </div>
        )}

        {/* Détails techniques (allocation, séniorité) */}
        <div className="p-5 grid grid-cols-2 gap-3 text-[11px]">
          <DetailItem label="Allocation"     value={`${assignment.allocated_sp} SP`} />
          <DetailItem label="Séniorité"      value={assignment.employee_seniority} />
          <DetailItem label="Job title"      value={assignment.job_title} />
          <DetailItem label="Statut profil"  value={PROFILE_STATUS_LABEL[assignment.status]?.label ?? assignment.status} />
        </div>
      </div>
    </div>
  );
}


function SkillSection({ title, subtitle, color, skills }) {
  const colorMap = {
    emerald: { dot: "bg-emerald-500", chip: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    blue:    { dot: "bg-blue-500",    chip: "bg-blue-50    text-blue-700    border-blue-200" },
    rose:    { dot: "bg-rose-500",    chip: "bg-rose-50    text-rose-700    border-rose-200" },
  };
  const c = colorMap[color] ?? colorMap.emerald;
  return (
    <div className="px-5 py-4 border-b border-slate-200">
      <p className="text-[11px] font-semibold text-slate-700 flex items-center gap-2">
        <span className={clsx("w-2 h-2 rounded-full", c.dot)} />
        {title}
        <span className="ml-auto text-[10px] font-normal text-slate-400">
          {skills.length}
        </span>
      </p>
      <p className="text-[10px] text-slate-500 mt-0.5 mb-2">{subtitle}</p>
      <div className="flex flex-wrap gap-1">
        {skills.length > 0 ? (
          skills.map((s) => (
            <span
              key={s}
              className={clsx("text-[10px] font-medium px-1.5 py-0.5 rounded-full border", c.chip)}
            >
              {s}
            </span>
          ))
        ) : (
          <span className="text-[10px] text-slate-400 italic">Aucune.</span>
        )}
      </div>
    </div>
  );
}


function DetailItem({ label, value }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <p className="text-[9px] uppercase tracking-wide text-slate-400 font-semibold">{label}</p>
      <p className="text-xs font-semibold text-slate-700 mt-0.5 truncate">{value ?? "—"}</p>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Card d'un ProfileAssignment (un profil dans une story)
// ─────────────────────────────────────────────────────────────

function ProfileAssignmentCard({
  assignment,
  storyTitle,
  storyId,
  sprintNumber,
  sprintStart,
  sprintEnd,
  requiredSkills,
  projectId,
  onWhy,
  onRecruitmentRequest,
  onChangeAssignment,
}) {
  const statusCfg = PROFILE_STATUS_LABEL[assignment.status] ?? { label: assignment.status, cls: "bg-slate-100 text-slate-500 border-slate-200" };
  const isAssigned = assignment.status === "assigned" || assignment.status === "assigned_with_warning";
  const isError    = ["missing_profile", "capacity_gap", "no_available_candidate"].includes(assignment.status);
  // Bouton "Signaler un besoin RH" pour les statuts où aucun profil interne n'existe.
  const showRecruitButton = ["missing_profile", "no_available_candidate"].includes(assignment.status);
  const downgradeFrom = assignment.seniority_downgrade_from;

  const triggerRecruit = () => {
    onRecruitmentRequest({
      profile:        assignment.required_profile,
      requiredSkills: requiredSkills ?? [],
      requiredLevel:  assignment.required_level ?? null,
      sprintNumber,
      sprintStart,
      sprintEnd,
    });
  };

  return (
    <div className={clsx(
      "rounded-lg border p-3",
      isAssigned && assignment.status === "assigned" && "border-emerald-200 bg-emerald-50/40",
      isAssigned && assignment.status === "assigned_with_warning" && "border-amber-200 bg-amber-50/40",
      isError && "border-rose-200 bg-rose-50/40",
    )}>
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 min-w-0 flex-wrap">
          <span className="text-xs font-semibold text-slate-700">
            {assignment.required_profile}
          </span>
          <span className={clsx(
            "text-[10px] font-semibold px-1.5 py-0.5 rounded-full border whitespace-nowrap",
            statusCfg.cls,
          )}>
            {statusCfg.label}
          </span>
          <span className="text-[10px] text-slate-500 whitespace-nowrap">
            {assignment.allocated_sp} SP
          </span>
          {downgradeFrom && (
            <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-full border bg-orange-50 text-orange-700 border-orange-200 whitespace-nowrap">
              <ArrowDownCircle size={10} />
              Séniorité dégradée ({downgradeFrom} demandé)
            </span>
          )}
        </div>
      </div>

      {/* Affecté → afficher employé + score + bouton "Pourquoi ?" */}
      {isAssigned && (
        <div className="mt-2 flex items-center gap-3">
          <div className="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center shrink-0">
            <User size={13} className="text-slate-500" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs font-semibold text-slate-800">
                {assignment.employee_name}
              </span>
              <span className={clsx(
                "text-[9px] font-semibold px-1.5 py-0.5 rounded-full border",
                SENIORITY_BADGE[assignment.employee_seniority] ?? "bg-slate-100 text-slate-500 border-slate-200",
              )}>
                {assignment.employee_seniority}
              </span>
              {assignment.match_level && (
                <span className={clsx(
                  "text-[9px] font-semibold px-1.5 py-0.5 rounded-full border capitalize",
                  MATCH_LEVEL_BADGE[assignment.match_level] ?? "bg-slate-100 text-slate-500 border-slate-200",
                )}>
                  {assignment.match_level}
                </span>
              )}
              {assignment.skill_score != null && (
                <span className="text-[10px] text-slate-600 font-semibold">
                  {Math.round(assignment.skill_score * 100)}%
                </span>
              )}
            </div>
            {assignment.reason && (
              <p className="text-[10px] text-slate-500 italic mt-0.5 line-clamp-2">
                « {assignment.reason} »
              </p>
            )}
          </div>
          <div className="flex flex-col gap-1 shrink-0">
            <button
              type="button"
              onClick={() => onWhy(assignment)}
              className="flex items-center gap-1 text-[10px] font-medium text-violet-700 bg-violet-50 hover:bg-violet-100 border border-violet-200 px-2 py-1 rounded-lg transition-colors"
            >
              <Eye size={11} />
              Pourquoi&nbsp;?
            </button>
            {(assignment.alternative_candidates?.length ?? 0) > 1 && (
              <button
                type="button"
                onClick={() => onChangeAssignment({
                  sprintNumber,
                  storyId,
                  storyTitle,
                  requiredProfile:    assignment.required_profile,
                  currentEmployeeId:  assignment.employee_id,
                  allocatedSp:        assignment.allocated_sp,
                  alternatives:       assignment.alternative_candidates ?? [],
                })}
                className="flex items-center gap-1 text-[10px] font-medium text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 px-2 py-1 rounded-lg transition-colors"
                title="Choisir un autre collaborateur parmi les candidats évalués"
              >
                <RefreshCw size={11} />
                Changer
              </button>
            )}
          </div>
        </div>
      )}

      {/* Erreur (missing/capacity/no_available) */}
      {isError && (
        <div className="mt-2 space-y-2">
          <div className="flex items-start gap-2">
            <AlertCircle size={13} className="text-rose-500 shrink-0 mt-0.5" />
            <p className="text-[11px] text-rose-700 flex-1">
              {assignment.reason}
            </p>
          </div>
          {showRecruitButton && (
            <button
              type="button"
              onClick={triggerRecruit}
              className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-white bg-rose-600 hover:bg-rose-700 px-2.5 py-1.5 rounded-lg transition-colors"
            >
              <Mail size={11} />
              Signaler un besoin en recrutement
            </button>
          )}
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Card d'une StoryMatching
// ─────────────────────────────────────────────────────────────

function StoryMatchingRow({
  story,
  storyMeta,
  sprintNumber,
  sprintStart,
  sprintEnd,
  projectId,
  onWhy,
  onRecruitmentRequest,
  onChangeAssignment,
}) {
  // Identifiant utilisateur : Jira key si dispo, sinon fallback DB id (#N).
  const storyLabel = storyMeta?.jira_issue_key || `#${story.story_id}`;
  const [expanded, setExpanded] = useState(true);
  const requiredProfiles = useMemo(
    () => Array.from(new Set((story.assignments ?? []).map((a) => a.required_profile))),
    [story.assignments],
  );

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-start gap-2 px-3 py-2.5 text-left hover:bg-slate-50 transition-colors"
      >
        <div className="pt-0.5">
          {expanded ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
        </div>
        <div className="flex-1 min-w-0">
          {/* Titre complet (multi-ligne autorisé, non tronqué) */}
          <div className="flex items-start gap-2 flex-wrap">
            <span className="text-xs font-semibold text-slate-800 leading-snug whitespace-normal break-words">
              <span className="font-mono text-cyan-700">{storyLabel}</span> · {story.story_title}
            </span>
            <StatusBadge map={STORY_STATUS_BADGE} status={story.story_status} />
          </div>

          {/* Métadonnées rapides */}
          <div className="flex items-center gap-3 mt-1 text-[10px] text-slate-500 flex-wrap">
            <span>{story.story_points} SP</span>
            <span>Niveau requis : <strong>{story.required_level}</strong></span>
            <span>{story.assignments?.length ?? 0} profil(s)</span>
          </div>

          {/* Profils requis (chips violets) */}
          {requiredProfiles.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 mt-1.5">
              <span className="inline-flex items-center gap-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-400">
                <Briefcase size={9} /> Profils :
              </span>
              {requiredProfiles.map((p) => (
                <span
                  key={p}
                  className="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200 font-medium"
                >
                  {p}
                </span>
              ))}
            </div>
          )}

          {/* Compétences requises (chips bleues) */}
          {story.required_skills?.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 mt-1">
              <span className="text-[9px] font-semibold uppercase tracking-wide text-slate-400">
                Compétences :
              </span>
              {story.required_skills.map((s) => (
                <span
                  key={s}
                  className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 font-medium"
                >
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2">
          {story.assignments?.map((a, idx) => (
            <ProfileAssignmentCard
              key={`${a.required_profile}-${idx}`}
              assignment={a}
              storyTitle={story.story_title}
              storyId={story.story_id}
              sprintNumber={sprintNumber}
              sprintStart={sprintStart}
              sprintEnd={sprintEnd}
              requiredSkills={story.required_skills}
              projectId={projectId}
              onWhy={(ass) => onWhy({
                assignment: ass,
                storyTitle: story.story_title,
                requiredProfile: a.required_profile,
                requiredSkills: story.required_skills,
              })}
              onRecruitmentRequest={onRecruitmentRequest}
              onChangeAssignment={onChangeAssignment}
            />
          ))}
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Card d'un sprint complet
// ─────────────────────────────────────────────────────────────

function SprintCard({ sprint, projectId, storyMap = {}, dbSprint, allDbSprints, onSprintLifecycleChange, onWhy, onRecruitmentRequest, onChangeAssignment, defaultExpanded = false }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const team = sprint.recommended_team ?? [];

  // Inject sprint's recommended_team so ChangeAssignmentDialog can recompute real capacity.
  const handleChangeWithTeam = (payload) =>
    onChangeAssignment({ ...payload, recommendedTeam: team });

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-slate-50 transition-colors border-b border-slate-100"
      >
        {expanded ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-slate-800">Sprint {sprint.sprint_number}</span>
            <StatusBadge map={SPRINT_STATUS_BADGE} status={sprint.sprint_status} />
            <span className="text-[10px] text-slate-500">
              {sprint.start_date} → {sprint.end_date}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-0.5 text-[11px] text-slate-500">
            <span>{sprint.planned_story_points} SP planifiés</span>
            <span>{sprint.story_assignments?.length ?? 0} stories</span>
            <span>{team.length} membres recommandés</span>
            {sprint.issues?.length > 0 && (
              <span className="text-rose-600 font-medium">{sprint.issues.length} issue(s)</span>
            )}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="p-4 space-y-4">

          {/* Cycle de vie : démarrer / clôturer le sprint */}
          <SprintLifecycleControls
            dbSprint={dbSprint}
            allDbSprints={allDbSprints}
            projectId={projectId}
            sprintNumber={sprint.sprint_number}
            onChange={onSprintLifecycleChange}
          />

          {/* Équipe recommandée */}
          {team.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-[11px] font-semibold text-slate-700 flex items-center gap-1.5 mb-2">
                <Users size={11} /> Équipe recommandée pour ce sprint
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {team.map((m) => {
                  const pct = m.capacity_sp > 0 ? Math.round((m.assigned_sp / m.capacity_sp) * 100) : 0;
                  return (
                    <div key={m.employee_id} className="flex items-center gap-2 bg-white rounded border border-slate-200 px-2 py-1.5">
                      <div className="w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center shrink-0">
                        <User size={11} className="text-slate-500" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1 flex-wrap">
                          <span className="text-xs font-semibold text-slate-700 truncate">{m.name}</span>
                          <span className={clsx(
                            "text-[9px] font-semibold px-1 py-0 rounded border",
                            SENIORITY_BADGE[m.seniority] ?? "bg-slate-100 text-slate-500 border-slate-200",
                          )}>
                            {m.seniority}
                          </span>
                        </div>
                        <p className="text-[9px] text-slate-500 truncate">{m.job_title}</p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <div className="flex-1 h-1 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className={clsx(
                                "h-full",
                                pct >= 100 ? "bg-rose-500" : pct >= 80 ? "bg-amber-500" : "bg-emerald-500",
                              )}
                              style={{ width: `${Math.min(100, pct)}%` }}
                            />
                          </div>
                          <span className="text-[9px] font-semibold text-slate-600 whitespace-nowrap">
                            {m.assigned_sp}/{m.capacity_sp} SP
                          </span>
                        </div>
                      </div>
                      <span className="text-[9px] text-slate-500 whitespace-nowrap">
                        {m.stories_handled} stories
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Stories du sprint */}
          {sprint.story_assignments?.length > 0 ? (
            <div className="space-y-2">
              {sprint.story_assignments.map((s) => (
                <StoryMatchingRow
                  key={s.story_id}
                  story={s}
                  storyMeta={storyMap[s.story_id]}
                  sprintNumber={sprint.sprint_number}
                  sprintStart={sprint.start_date}
                  sprintEnd={sprint.end_date}
                  projectId={projectId}
                  onWhy={onWhy}
                  onRecruitmentRequest={onRecruitmentRequest}
                  onChangeAssignment={handleChangeWithTeam}
                />
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-400 italic text-center py-4">
              Aucune story planifiée dans ce sprint.
            </p>
          )}
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Composant principal
// ─────────────────────────────────────────────────────────────

export default function MatchingResultCard({ result, projectId, project, currentUserName, storyMap = {}, onRefresh }) {
  const [drawer, setDrawer]               = useState({ open: false, payload: null });
  const [recruitDialog, setRecruitDialog] = useState({ open: false, payload: null });
  const [changeDialog, setChangeDialog]   = useState({ open: false, payload: null });
  const [rerunning, setRerunning]         = useState(false);
  const [rerunError, setRerunError]       = useState(null);
  const [rerunSuccess, setRerunSuccess]   = useState(false);
  const [activeSprintKey, setActiveSprintKey] = useState(null);

  // ── DB sprints (pm.sprints) pour le cycle de vie démarrer/clôturer ──
  // Vide tant que la phase staffing n'est pas validée (jira_sync les persiste).
  const [dbSprints, setDbSprints] = useState([]);

  const reloadDbSprints = useCallback(async () => {
    if (!projectId) return;
    try {
      const data = await getProjectSprints(projectId);
      setDbSprints(Array.isArray(data) ? data : []);
    } catch {
      setDbSprints([]);
    }
  }, [projectId]);

  useEffect(() => {
    reloadDbSprints();
  }, [reloadDbSprints]);

  const dbSprintByNumber = useMemo(() => {
    const m = new Map();
    for (const s of dbSprints) m.set(s.sprint_number, s);
    return m;
  }, [dbSprints]);

  const sprintsArr = useMemo(() => {
    const map = result?.matching_by_sprint ?? {};
    return Object.entries(map)
      .map(([k, v]) => ({ key: k, ...v }))
      .sort((a, b) => (a.sprint_number ?? 0) - (b.sprint_number ?? 0));
  }, [result]);

  if (!result || !result.matching_by_sprint) {
    return (
      <p className="text-sm text-slate-400 italic text-center py-8">
        Aucun résultat de matching disponible.
      </p>
    );
  }

  const summary = result.global_summary ?? {};
  const projectName = project?.name ?? `Projet #${projectId}`;

  const handleWhy = (payload) => setDrawer({ open: true, payload });
  const handleRecruitmentRequest = (payload) => setRecruitDialog({ open: true, payload });
  const handleChangeAssignment = (payload) => setChangeDialog({ open: true, payload });

  const handleRerun = async () => {
    setRerunning(true);
    setRerunError(null);
    setRerunSuccess(false);
    try {
      await rerunMatching(projectId);
      setRerunSuccess(true);
      // Laisser le temps au backend de calculer puis rafraîchir l'état du pipeline.
      // L'execution est en background côté serveur — on poll via onRefresh dans 4s.
      setTimeout(() => {
        onRefresh?.();
        setRerunSuccess(false);
      }, 4000);
    } catch (e) {
      setRerunError(e?.response?.data?.detail ?? "Échec du relancement.");
    } finally {
      setRerunning(false);
    }
  };

  return (
    <div className="space-y-4">

      {/* Barre d'actions globales */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-[11px] text-slate-500">
          Affectation calculée à partir des candidats internes disponibles. Si RH a
          ajouté de nouveaux profils, relance l&apos;analyse pour réévaluer.
        </div>
        <div className="flex items-center gap-2">
          {rerunError && (
            <span className="text-[11px] text-rose-600 bg-rose-50 border border-rose-200 rounded px-2 py-0.5">
              {rerunError}
            </span>
          )}
          {rerunSuccess && !rerunError && (
            <span className="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-0.5">
              Recalcul lancé en arrière-plan…
            </span>
          )}
          <button
            type="button"
            onClick={handleRerun}
            disabled={rerunning}
            className={clsx(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors",
              "border border-navy/20 text-navy bg-white hover:bg-navy/5 disabled:opacity-50",
            )}
            title="Recalcule uniquement le matching, sans toucher aux étapes amont."
          >
            <RefreshCw size={12} className={rerunning ? "animate-spin" : ""} />
            {rerunning ? "Relancement…" : "Relancer l'analyse"}
          </button>
        </div>
      </div>

      {/* Résumé global */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <SummaryCard
          label="Sprints complets"
          value={`${summary.fully_staffed_sprints ?? 0}/${summary.total_sprints ?? 0}`}
          tone="emerald"
          Icon={CheckCircle}
        />
        <SummaryCard
          label="Sprints partiels"
          value={summary.partially_staffed_sprints ?? 0}
          tone="amber"
          Icon={AlertTriangle}
        />
        <SummaryCard
          label="Avec alerte"
          value={summary.assignments_with_warning ?? 0}
          tone="orange"
          Icon={AlertCircle}
        />
      </div>

      {summary.missing_profiles?.length > 0 && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3">
          <p className="text-xs font-semibold text-rose-700 mb-1 flex items-center gap-1.5">
            <Users size={12} /> Profils à recruter ({summary.missing_profiles.length})
          </p>
          <div className="flex flex-wrap gap-1 mt-1">
            {summary.missing_profiles.map((p) => (
              <span
                key={p}
                className="text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-white text-rose-700 border-rose-200"
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Tabs sprints */}
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5 border-b border-slate-200 pb-2">
          {sprintsArr.map((sprint) => {
            const isActive = activeSprintKey === sprint.key;
            const cfg = SPRINT_STATUS_BADGE[sprint.sprint_status] ?? {};
            const Icon = cfg.Icon ?? Info;
            return (
              <button
                key={sprint.key}
                type="button"
                onClick={() => setActiveSprintKey(isActive ? null : sprint.key)}
                className={clsx(
                  "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors",
                  isActive
                    ? "bg-navy text-white border-navy"
                    : "bg-white text-slate-700 border-slate-200 hover:border-slate-300 hover:bg-slate-50",
                )}
              >
                <span>Sprint {sprint.sprint_number}</span>
                <Icon size={11} className={isActive ? "text-white" : "text-slate-500"} />
                {sprint.issues?.length > 0 && (
                  <span className={clsx(
                    "ml-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full",
                    isActive ? "bg-white text-rose-700" : "bg-rose-100 text-rose-700",
                  )}>
                    {sprint.issues.length}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {activeSprintKey ? (
          (() => {
            const sprint = sprintsArr.find((s) => s.key === activeSprintKey);
            if (!sprint) return null;
            return (
              <SprintCard
                key={sprint.key}
                sprint={sprint}
                projectId={projectId}
                storyMap={storyMap}
                dbSprint={dbSprintByNumber.get(sprint.sprint_number)}
                allDbSprints={dbSprints}
                onSprintLifecycleChange={() => { reloadDbSprints(); onRefresh?.(); }}
                onWhy={handleWhy}
                onRecruitmentRequest={handleRecruitmentRequest}
                onChangeAssignment={handleChangeAssignment}
                defaultExpanded={true}
              />
            );
          })()
        ) : (
          <p className="text-xs text-slate-400 italic text-center py-6">
            Sélectionne un sprint ci-dessus pour voir le détail des affectations.
          </p>
        )}
      </div>

      {/* Drawer explainability */}
      <ExplainabilityDrawer
        open={drawer.open}
        onClose={() => setDrawer({ open: false, payload: null })}
        assignment={drawer.payload?.assignment}
        storyTitle={drawer.payload?.storyTitle}
        requiredProfile={drawer.payload?.requiredProfile}
        requiredSkills={drawer.payload?.requiredSkills}
      />

      {/* Dialog recruitment request */}
      <RecruitmentRequestDialog
        open={recruitDialog.open}
        onClose={() => setRecruitDialog({ open: false, payload: null })}
        projectId={projectId}
        projectName={projectName}
        profile={recruitDialog.payload?.profile}
        requiredSkills={recruitDialog.payload?.requiredSkills}
        requiredLevel={recruitDialog.payload?.requiredLevel}
        sprintNumber={recruitDialog.payload?.sprintNumber}
        sprintStart={recruitDialog.payload?.sprintStart}
        sprintEnd={recruitDialog.payload?.sprintEnd}
        pmName={currentUserName}
        onSent={onRefresh}
      />

      {/* Dialog change assignment */}
      <ChangeAssignmentDialog
        open={changeDialog.open}
        onClose={() => setChangeDialog({ open: false, payload: null })}
        projectId={projectId}
        sprintNumber={changeDialog.payload?.sprintNumber}
        storyId={changeDialog.payload?.storyId}
        storyTitle={changeDialog.payload?.storyTitle}
        requiredProfile={changeDialog.payload?.requiredProfile}
        currentEmployeeId={changeDialog.payload?.currentEmployeeId}
        allocatedSp={changeDialog.payload?.allocatedSp}
        recommendedTeam={changeDialog.payload?.recommendedTeam}
        alternatives={changeDialog.payload?.alternatives}
        onResolved={onRefresh}
      />
    </div>
  );
}


function SummaryCard({ label, value, tone, Icon }) {
  const toneMap = {
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-700",
    amber:   "bg-amber-50   border-amber-200   text-amber-700",
    violet:  "bg-violet-50  border-violet-200  text-violet-700",
    orange:  "bg-orange-50  border-orange-200  text-orange-700",
  };
  return (
    <div className={clsx("rounded-lg border px-3 py-2.5", toneMap[tone])}>
      <div className="flex items-center gap-1.5 mb-0.5">
        <Icon size={12} />
        <p className="text-[10px] font-semibold uppercase tracking-wide">{label}</p>
      </div>
      <p className="text-lg font-bold">{value}</p>
    </div>
  );
}
