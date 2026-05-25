// client/src/pages/pm/components/MonitoringSection.jsx
// ─────────────────────────────────────────────────────────────────────────────
// Rendu de la phase "Monitoring" (phase 8) dans la page projet (/projet/:id).
// Branché via PhaseResult.jsx quand phaseId === "monitoring".
//
// Contrairement à DeliverySection (dashboard PM, vue portefeuille), cet
// onglet expose le DÉTAIL sprint par sprint du projet courant :
//   - bandeau "Retard cumulé : +Xj / -Xj / à l'heure" + insight texte
//   - une ligne par sprint avec :
//       * planifié vs réel (dates + delta en jours, en avance / en retard)
//       * jours restants ou débordement pour le sprint actif
//       * charge story-points (actual / target)
//
// Source de données : getProjectMonitoringDelivery(projectId)
//                     → GET /pipeline/{id}/monitoring/delivery
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect, useState } from "react";
import {
  Activity, AlertTriangle, CheckCircle, Clock, Calendar,
  PlayCircle, PauseCircle, Loader,
} from "lucide-react";
import clsx from "clsx";
import { getProjectMonitoringDelivery } from "../../../api/pm";

// ─── Helpers ────────────────────────────────────────────────────────
function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso + "T00:00:00").toLocaleDateString("fr-FR", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch { return iso; }
}

function offsetText(days) {
  // null = pas encore mesurable
  if (days == null) return null;
  if (days > 0) return { label: `+${days}j (retard)`, cls: "text-red-600" };
  if (days < 0) return { label: `${days}j (avance)`, cls: "text-green-600" };
  return { label: "à l'heure", cls: "text-slate-500" };
}

const SPRINT_STATUS_CFG = {
  planned:   { label: "Planifié",   icon: PauseCircle, cls: "bg-slate-100 text-slate-500" },
  active:    { label: "En cours",   icon: PlayCircle,  cls: "bg-cyan-50 text-cyan-700" },
  completed: { label: "Clôturé",    icon: CheckCircle, cls: "bg-green-50 text-green-700" },
};

// ─── Carte projet (entête) ──────────────────────────────────────────
function ProjectInsightCard({ summary }) {
  const cum = summary.cumulative_delay_days;
  const tone =
    cum > 5  ? { bg: "bg-red-50",   border: "border-red-200",   text: "text-red-700",   icon: AlertTriangle } :
    cum > 0  ? { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", icon: AlertTriangle } :
    cum < 0  ? { bg: "bg-green-50", border: "border-green-200", text: "text-green-700", icon: CheckCircle } :
               { bg: "bg-slate-50", border: "border-slate-200", text: "text-slate-600", icon: Clock };
  const Icon = tone.icon;

  return (
    <div className={clsx("rounded-xl border p-4", tone.bg, tone.border)}>
      <div className="flex items-start gap-3">
        <Icon size={18} className={clsx("shrink-0 mt-0.5", tone.text)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className={clsx("text-sm font-semibold", tone.text)}>
              {cum > 0 && `Retard cumulé : +${cum} jour${cum > 1 ? "s" : ""}`}
              {cum < 0 && `Avance cumulée : ${cum} jour${-cum > 1 ? "s" : ""}`}
              {cum === 0 && "Sur le planning"}
            </span>
            <span className="text-xs text-slate-500">
              · {summary.completed_sprints}/{summary.total_sprints} sprints clôturés
              {summary.progress_pct ? ` · ${summary.progress_pct}%` : ""}
            </span>
          </div>
          <p className="text-xs text-slate-600 mt-1 leading-relaxed">
            {summary.insight}
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Ligne sprint ──────────────────────────────────────────────────
function SprintRow({ s }) {
  const cfg = SPRINT_STATUS_CFG[s.status] ?? SPRINT_STATUS_CFG.planned;
  const StatusIcon = cfg.icon;
  const startOff = offsetText(s.start_offset_days);
  const endOff   = offsetText(s.end_offset_days);

  // Statut temporel du sprint actif : restant ou débordement
  let timeBadge = null;
  if (s.status === "active") {
    if (s.days_overdue != null) {
      timeBadge = (
        <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-red-50 text-red-600">
          <AlertTriangle size={10} /> +{s.days_overdue}j de débordement
        </span>
      );
    } else if (s.days_remaining != null) {
      timeBadge = (
        <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-cyan-50 text-cyan-700">
          <Clock size={10} /> {s.days_remaining}j restants
        </span>
      );
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 p-3 space-y-2">
      {/* En-tête ligne sprint */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={clsx("inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full", cfg.cls)}>
          <StatusIcon size={11} /> {cfg.label}
        </span>
        <span className="text-sm font-semibold text-slate-800">
          {s.name || `Sprint ${s.sprint_number}`}
        </span>
        {timeBadge}
      </div>

      {/* Dates planifié vs réel */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-slate-50 rounded-lg px-3 py-2">
          <div className="text-[11px] text-slate-400 uppercase tracking-wide mb-0.5">
            <Calendar size={9} className="inline mr-1" /> Démarrage
          </div>
          <div className="text-slate-700">
            Planifié : <span className="font-medium">{formatDate(s.planned_start)}</span>
          </div>
          <div className="text-slate-700">
            Réel : <span className="font-medium">{formatDate(s.actual_start)}</span>
            {startOff && <span className={clsx("ml-1.5 font-medium", startOff.cls)}>· {startOff.label}</span>}
          </div>
        </div>
        <div className="bg-slate-50 rounded-lg px-3 py-2">
          <div className="text-[11px] text-slate-400 uppercase tracking-wide mb-0.5">
            <Calendar size={9} className="inline mr-1" /> Clôture
          </div>
          <div className="text-slate-700">
            Planifiée : <span className="font-medium">{formatDate(s.planned_end)}</span>
          </div>
          <div className="text-slate-700">
            Réelle : <span className="font-medium">{formatDate(s.actual_end)}</span>
            {endOff && <span className={clsx("ml-1.5 font-medium", endOff.cls)}>· {endOff.label}</span>}
          </div>
        </div>
      </div>

      {/* Charge story-points */}
      {s.target_capacity_sp > 0 && (
        <div>
          <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
            <span>Charge story-points</span>
            <span>
              <span className="font-medium text-slate-700">{s.actual_sp}</span>
              <span className="text-slate-400"> / {s.target_capacity_sp} SP · {s.capacity_load_pct}%</span>
            </span>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
            <div
              className={clsx(
                "h-1.5 rounded-full",
                s.capacity_load_pct > 100 ? "bg-red-500" :
                s.capacity_load_pct > 85  ? "bg-amber-500" : "bg-cyan"
              )}
              style={{ width: `${Math.min(s.capacity_load_pct, 100)}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Composant racine ──────────────────────────────────────────────
export default function MonitoringSection({ projectId }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    getProjectMonitoringDelivery(projectId)
      .then(setData)
      .catch(e => setError(e?.response?.data?.detail ?? "Erreur de chargement."))
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-400 text-sm py-6">
        <Loader size={15} className="animate-spin"/> Chargement du monitoring...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
        <AlertTriangle size={14}/> {error}
      </div>
    );
  }

  if (!data) return null;

  const { project: summary, sprints } = data;

  return (
    <div className="space-y-4">
      {/* Insight projet */}
      <ProjectInsightCard summary={summary} />

      {/* Liste des sprints */}
      {sprints.length === 0 ? (
        <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm text-slate-500">
          <Activity size={14}/> Aucun sprint planifié pour ce projet.
        </div>
      ) : (
        <div className="space-y-2">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
            Sprints du projet ({sprints.length})
          </div>
          {sprints.map(s => <SprintRow key={s.sprint_number} s={s} />)}
        </div>
      )}
    </div>
  );
}
