// client/src/pages/pm/components/DeliverySection.jsx
// ─────────────────────────────────────────────────────────────────────────────
// Section "Pilotage des livraisons" du Dashboard PM (/dashboard).
//
// Affichée UNIQUEMENT dans le dashboard PM. Le détail sprint par sprint
// d'un projet vit dans l'onglet Monitoring du projet (MonitoringSection.jsx),
// pas ici — volontairement.
//
// Contenu :
//   1) 6 cartes de statut (une par valeur de ProjectGlobalStatus) avec count
//   2) Liste filtrée par statut (dropdown, défaut : in_development)
//   3) Carte "Projets à risque" : ranking par retard cumulé (jours)
//   4) Carte "Retards des sprints clos" : 3 barres (En avance / À l'heure / En retard)
//   5) Carte "Répartition des statuts" : donut Recharts
//   6) Carte "Vélocité (8 semaines)" : barres sprints clos par semaine
//
// Source de données : getPMDelivery() → GET /dashboard/pm/delivery
// ─────────────────────────────────────────────────────────────────────────────

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";
import {
  Activity, AlertTriangle, ArrowRight, AlertCircle,
  CheckCircle, Clock, PackageCheck, Circle, Cpu,
  UserCheck, CheckSquare, Code2, ChevronDown,
  CalendarDays, Users,
} from "lucide-react";
import clsx from "clsx";
import StatusBadge from "./StatusBadge";

// ── Config par statut (icône, couleur, libellé, description courte) ──────────
const STATUS_CONFIG = {
  not_started:    {
    icon: Circle,       color: "bg-slate-100 text-slate-500",  dot: "#94a3b8",
    label: "Non démarré",      desc: "Aucune phase pipeline lancée",
  },
  in_progress:    {
    icon: Cpu,          color: "bg-blue-50 text-blue-600",     dot: "#3b82f6",
    label: "Pipeline IA",      desc: "Pipeline IA en cours d'exécution",
  },
  pending_human:  {
    icon: UserCheck,    color: "bg-amber-50 text-amber-600",   dot: "#f59e0b",
    label: "Validation PM",    desc: "En attente de votre validation",
  },
  pipeline_done:  {
    icon: CheckSquare,  color: "bg-violet-50 text-violet-600", dot: "#8b5cf6",
    label: "Prêt pour le développement", desc: "Pipeline validé, développement à lancer",
  },
  in_development: {
    icon: Code2,        color: "bg-cyan-50 text-cyan-700",     dot: "#00B4D8",
    label: "En développement", desc: "Développement en cours",
  },
  delivered:      {
    icon: PackageCheck, color: "bg-green-50 text-green-600",   dot: "#22c55e",
    label: "Livré",            desc: "Projet livré avec succès",
  },
};

const STATUS_ORDER = [
  "not_started", "in_progress", "pending_human",
  "pipeline_done", "in_development", "delivered",
];

const DELAY_BUCKET_COLOR = {
  early:   "#22c55e",
  on_time: "#00B4D8",
  late:    "#ef4444",
};

// ─── Helpers ────────────────────────────────────────────────────────
function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso + "T00:00:00").toLocaleDateString("fr-FR", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch { return iso; }
}

function delayChip(days) {
  if (days > 0) return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-red-50 text-red-600">
      <AlertTriangle size={10} /> +{days}j
    </span>
  );
  if (days < 0) return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700">
      <CheckCircle size={10} /> {days}j
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
      <Clock size={10} /> À l'heure
    </span>
  );
}

// ─── 1) Carte de statut — informative uniquement (filtre via le dropdown) ─────
function StatusCard({ statusKey, count }) {
  const cfg = STATUS_CONFIG[statusKey] || STATUS_CONFIG.not_started;
  const Icon = cfg.icon;
  return (
    <div className="card p-4">
      <div className={clsx("w-9 h-9 rounded-xl flex items-center justify-center mb-3", cfg.color)}>
        <Icon size={17} />
      </div>
      <div className="text-2xl font-display font-bold text-navy">{count}</div>
      <div className="text-sm font-medium text-slate-700 mt-0.5">{cfg.label}</div>
      <div className="text-xs text-slate-400 mt-0.5 leading-tight">{cfg.desc}</div>
    </div>
  );
}

// ─── Helper : badge offset démarrage sprint ──────────────────────────────────
function startOffsetBadge(offset) {
  if (offset == null) return null;
  if (offset < 0) return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700">
      <CheckCircle size={9} /> Démarré {-offset}j en avance
    </span>
  );
  if (offset > 0) return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-red-50 text-red-600">
      <AlertTriangle size={9} /> Démarré {offset}j en retard
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
      <Clock size={9} /> Démarré à la date prévue
    </span>
  );
}

// ─── Badge "N personnes" avec tooltip au hover ───────────────────────────────
// Stoppe la propagation du clic pour ne pas déclencher la navigation.
function AssigneesBadge({ assignees, count }) {
  return (
    <div
      className="relative inline-block mt-1.5"
      onClick={e => e.stopPropagation()}
    >
      {/* Déclencheur : badge discret */}
      <div className="group inline-flex items-center gap-1.5 text-xs text-slate-500 cursor-default">
        <Users size={11} className="text-slate-400 shrink-0" />
        <span className="font-medium text-slate-700 underline decoration-dotted underline-offset-2">
          {count} personne{count > 1 ? "s" : ""} affectée{count > 1 ? "s" : ""}
        </span>

        {/* Tooltip positionné en-dessous */}
        <div className="
          pointer-events-none absolute left-0 top-full mt-1.5 z-50
          invisible opacity-0 group-hover:visible group-hover:opacity-100
          transition-opacity duration-150
          w-64 bg-white border border-slate-200 rounded-xl shadow-lg p-2 space-y-1
        ">
          {assignees.map((a, i) => (
            <div key={i} className="flex items-start gap-2 p-1.5 rounded-lg hover:bg-slate-50">
              {/* Avatar initiales */}
              <div className="w-7 h-7 rounded-full bg-cyan-50 text-cyan-700 flex items-center justify-center text-[10px] font-bold shrink-0">
                {(a.name || "?").split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-800 truncate">{a.name || "—"}</div>
                <div className="text-[11px] text-slate-500 truncate">{a.job_title || "—"}</div>
                {(a.team || a.department) && (
                  <div className="text-[10px] text-slate-400 truncate mt-0.5">
                    {[a.team, a.department].filter(Boolean).join(" · ")}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── 2) Carte projet (dans la liste filtrée) ─────────────────────────────────
function ProjectCard({ p, onClick }) {
  const total = p.total_sprints || 0;
  const cur   = p.current_sprint_number;
  const barColor =
    p.cumulative_delay_days > 5 ? "bg-red-500" :
    p.cumulative_delay_days > 0 ? "bg-amber-500" :
    "bg-cyan";

  // Infos sprint courant — affichées uniquement si le sprint a démarré
  const hasSprintStarted = p.status === "in_development" && p.current_sprint_actual_start;
  const assigneeCount = p.current_sprint_assignee_count || 0;

  return (
    <button
      onClick={onClick}
      className="w-full text-left p-3 bg-slate-50 hover:bg-slate-100 rounded-xl transition-colors"
    >
      {/* Nom + client + badge statut */}
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-800 truncate">{p.name}</div>
          <div className="text-xs text-slate-400 truncate">{p.client_name}</div>
        </div>
        <StatusBadge status={p.status} />
      </div>

      {/* Barre de progression */}
      <div className="w-full bg-slate-200 rounded-full h-1.5 mt-2 overflow-hidden">
        <div className={clsx("h-1.5 rounded-full transition-all", barColor)}
             style={{ width: `${p.progress_pct}%` }} />
      </div>

      {/* Sprint + % + deadline + chip retard cumulé */}
      <div className="flex items-center justify-between text-xs text-slate-500 mt-1.5">
        <span>
          {total > 0 && cur
            ? `Sprint ${cur}/${total} · ${p.progress_pct}%`
            : `${p.progress_pct}%`}
          {p.deadline && <> · deadline {formatDate(p.deadline)}</>}
        </span>
        {delayChip(p.cumulative_delay_days)}
      </div>

      {/* Dates du sprint courant + offset démarrage (seulement si sprint actif) */}
      {hasSprintStarted && (
        <div className="mt-2 space-y-1.5">
          <div className="flex items-center gap-3 text-xs text-slate-600 flex-wrap">
            <span className="flex items-center gap-1">
              <CalendarDays size={11} className="text-slate-400 shrink-0" />
              Démarré le <span className="font-medium ml-1">{formatDate(p.current_sprint_actual_start)}</span>
            </span>
            <span className="text-slate-300">·</span>
            <span className="flex items-center gap-1">
              Fin prévue <span className="font-medium ml-1">{formatDate(p.current_sprint_planned_end)}</span>
            </span>
          </div>
          {startOffsetBadge(p.current_sprint_start_offset)}
        </div>
      )}

      {/* Personnes affectées — badge cliquable avec tooltip au hover */}
      {hasSprintStarted && assigneeCount > 0 && (
        <AssigneesBadge assignees={p.current_sprint_assignees || []} count={assigneeCount} />
      )}

      {/* Insight texte */}
      <p className="text-xs text-slate-500 mt-1.5 leading-snug">{p.insight}</p>
    </button>
  );
}

// ─── 3) Ranking "Projets à risque" ──────────────────────────────────────────
function AtRiskList({ items, onProjectClick }) {
  if (!items.length) {
    return (
      <p className="text-xs text-slate-400 py-6 text-center">
        Aucun projet en retard.{" "}
        <span className="text-slate-500">Bon pilotage 🎯</span>
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {items.map(p => {
        const src = p.delay_source;
        return (
          <button
            key={p.id}
            onClick={() => onProjectClick(p.id)}
            className="w-full p-3 hover:bg-slate-50 rounded-xl transition-colors text-left border border-transparent hover:border-slate-200"
          >
            {/* Ligne 1 : nom + chip retard */}
            <div className="flex items-center justify-between gap-2 mb-1">
              <div className="text-sm font-semibold text-slate-800 truncate">{p.name}</div>
              <div className="flex items-center gap-1.5 shrink-0">
                {delayChip(p.cumulative_delay_days)}
                <ArrowRight size={12} className="text-slate-300" />
              </div>
            </div>

            {/* Ligne 2 : client + sprint courant */}
            <div className="text-xs text-slate-400 mb-1.5">
              {p.client_name}
              {p.current_sprint_number && p.total_sprints
                ? ` · Sprint ${p.current_sprint_number}/${p.total_sprints}`
                : ""}
            </div>

            {/* Ligne 3 : source du retard */}
            {src && (
              <div className={clsx(
                "inline-flex items-center gap-1.5 text-[11px] font-medium px-2 py-1 rounded-lg",
                src.type === "overdue"
                  ? "bg-red-50 text-red-600"
                  : "bg-amber-50 text-amber-700",
              )}>
                <AlertTriangle size={10} />
                {src.type === "overdue" ? (
                  <>Sprint {src.sprint_number} en débordement · prévu le {formatDate(src.planned_end)}</>
                ) : (
                  <>Sprint {src.sprint_number} clôturé avec +{src.days}j de retard · prévu le {formatDate(src.planned_end)}</>
                )}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ─── 4) Distribution retards des sprints clos (3 buckets) ────────────────────
function SprintDelayDistribution({ data, activeOverdueCount }) {
  const total = data.reduce((s, d) => s + d.count, 0);
  return (
    <div className="space-y-3">
      {/* Indicateur sprints actifs en débordement (pas encore clos) */}
      {activeOverdueCount > 0 && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
          <AlertTriangle size={12} className="text-red-500 shrink-0" />
          <span className="text-xs text-red-600 font-medium">
            {activeOverdueCount} sprint{activeOverdueCount > 1 ? "s" : ""} actif{activeOverdueCount > 1 ? "s" : ""} en débordement
          </span>
          <span className="text-[11px] text-red-400 ml-auto">non encore clôturé{activeOverdueCount > 1 ? "s" : ""}</span>
        </div>
      )}

      {/* 3 buckets sprints clos */}
      {total === 0 ? (
        <p className="text-xs text-slate-400 py-4 text-center">
          Aucun sprint clôturé pour l'instant.
        </p>
      ) : (
        data.map(b => {
          const pct = total ? Math.round(b.count / total * 100) : 0;
          return (
            <div key={b.bucket}>
              <div className="flex items-center justify-between text-xs text-slate-600 mb-1">
                <span className="font-medium">{b.label}</span>
                <span className="text-slate-400">
                  {b.count} sprint{b.count > 1 ? "s" : ""} · {pct}%
                </span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                <div
                  className="h-2 rounded-full"
                  style={{ width: `${pct}%`, background: DELAY_BUCKET_COLOR[b.bucket] }}
                />
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

// ─── 5) Donut statuts ────────────────────────────────────────────────────────
function StatusDonut({ data }) {
  const total = data.reduce((s, d) => s + d.count, 0);
  if (total === 0) {
    return <p className="text-xs text-slate-400 py-6 text-center">Aucun projet.</p>;
  }
  const enriched = data.map(d => ({
    ...d,
    label: STATUS_CONFIG[d.status]?.label || d.status,
    color: STATUS_CONFIG[d.status]?.dot   || "#94a3b8",
  }));
  return (
    <div className="flex items-center gap-4">
      <div className="w-32 h-32 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={enriched} dataKey="count" nameKey="label"
              innerRadius={32} outerRadius={58} paddingAngle={2} stroke="none"
            >
              {enriched.map((e, i) => <Cell key={i} fill={e.color} />)}
            </Pie>
            <Tooltip
              formatter={(v, n) => [`${v} projet${v > 1 ? "s" : ""}`, n]}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex-1 space-y-1.5">
        {enriched.map(e => (
          <div key={e.status} className="flex items-center gap-2 text-xs">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: e.color }} />
            <span className="text-slate-600 flex-1 truncate">{e.label}</span>
            <span className="text-slate-400 font-medium">{e.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── 6) Vélocité hebdo (8 semaines) ─────────────────────────────────────────

// Tooltip custom : affiche la plage de dates + le détail de chaque sprint clos
function VelocityTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const { label, completed, sprints } = payload[0].payload;
  if (completed === 0) return null;

  // Total SP réalisés sur toute la semaine
  const totalSp = sprints.reduce((sum, s) => sum + (s.actual_sp || 0), 0);

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-lg p-3 text-xs min-w-[220px]">
      {/* En-tête : plage + résumé semaine */}
      <div className="font-semibold text-slate-700 mb-1">{label}</div>
      <div className="flex items-center gap-3 text-slate-400 mb-3 pb-2 border-b border-slate-100">
        <span>{completed} sprint{completed > 1 ? "s" : ""} clôturé{completed > 1 ? "s" : ""}</span>
        {totalSp > 0 && (
          <>
            <span className="text-slate-200">·</span>
            <span className="font-medium text-cyan-600">{totalSp} SP réalisés</span>
          </>
        )}
      </div>

      {/* Détail par sprint */}
      {sprints.map((s, i) => (
        <div key={i} className={clsx("py-1.5 flex items-start gap-2", i > 0 && "border-t border-slate-100")}>
          <div className="w-1.5 h-1.5 rounded-full bg-cyan shrink-0 mt-1.5" />
          <div className="flex-1 min-w-0">
            <div className="font-medium text-slate-800 truncate">
              Sprint {s.sprint_number} · {s.project_name}
            </div>
            <div className="text-slate-400 mt-0.5">
              Clôturé le {formatDate(s.actual_end_date)}
            </div>
            {s.target_capacity_sp > 0 && (
              <div className="mt-1 flex items-center gap-1.5">
                <div className="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="h-1.5 rounded-full bg-cyan"
                    style={{ width: `${Math.min(Math.round((s.actual_sp / s.target_capacity_sp) * 100), 100)}%` }}
                  />
                </div>
                <span className="text-slate-500 whitespace-nowrap">
                  {s.actual_sp}/{s.target_capacity_sp} SP
                </span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function VelocityChart({ data }) {
  return (
    <div>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ left: 10, right: 8, top: 4, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 9, fill: "#64748b" }}
              interval={0}
              angle={-35}
              textAnchor="end"
              height={52}
            />
            <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#64748b" }} width={20} />
            <Tooltip content={<VelocityTooltip />} cursor={{ fill: "#f1f5f9" }} />
            <Bar dataKey="completed" fill="#00B4D8" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── Section racine ──────────────────────────────────────────────────────────
export default function DeliverySection({ data, loading }) {
  const nav = useNavigate();
  // Dropdown : filtre la liste de projets, défaut = "in_development"
  const [selectedStatus, setSelectedStatus] = useState("in_development");

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-28 bg-slate-100 rounded-2xl animate-pulse" />
          ))}
        </div>
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="h-64 bg-slate-100 rounded-2xl animate-pulse" />
          <div className="h-64 bg-slate-100 rounded-2xl animate-pulse" />
        </div>
      </div>
    );
  }

  if (!data || data.kpis.total_projects === 0) return null;

  const {
    kpis, all_projects, at_risk_projects,
    status_distribution, sprint_delay_distribution, velocity_weekly,
    active_overdue_sprint_count,
  } = data;

  // Compter par statut à partir de status_distribution
  const countByStatus = Object.fromEntries(
    status_distribution.map(d => [d.status, d.count])
  );

  // Filtrer la liste de projets selon le statut sélectionné
  const filteredProjects = selectedStatus
    ? (all_projects || []).filter(p => p.status === selectedStatus)
    : (all_projects || []);

  const selectedCfg = STATUS_CONFIG[selectedStatus];

  return (
    <div className="space-y-5">
      {/* Titre de section */}
      <div className="flex items-center gap-2">
        <Activity size={17} className="text-cyan shrink-0" />
        <h2 className="font-display font-bold text-navy text-base">
          Pilotage des livraisons
        </h2>
        <span className="text-xs text-slate-400 ml-1">
          · sur la base des sprints planifiés vs réels
        </span>
      </div>

      {/* 6 cartes de statut — affichage informatif, filtre via le dropdown */}
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
        {STATUS_ORDER.map(key => (
          <StatusCard
            key={key}
            statusKey={key}
            count={countByStatus[key] ?? 0}
          />
        ))}
      </div>

      {/* Analytics — 3 charts compacts pour une vue d'ensemble rapide */}
      <div className="grid lg:grid-cols-3 gap-5">
        <div className="card p-5">
          <h3 className="font-display font-bold text-navy text-sm mb-3">
            Retards des sprints clos
          </h3>
          <SprintDelayDistribution
            data={sprint_delay_distribution}
            activeOverdueCount={active_overdue_sprint_count || 0}
          />
        </div>

        <div className="card p-5">
          <h3 className="font-display font-bold text-navy text-sm mb-3">
            Répartition des statuts
          </h3>
          <StatusDonut data={status_distribution} />
        </div>

        <div className="card p-5">
          <h3 className="font-display font-bold text-navy text-sm mb-3">
            Vélocité — sprints clôturés par semaine
          </h3>
          <VelocityChart data={velocity_weekly} />
        </div>
      </div>

      {/* Opérationnel — Liste projets filtrable + Projets à risque (drill-down) */}
      <div className="grid lg:grid-cols-2 gap-5">
        <div className="card p-5">
          <div className="flex items-center justify-between mb-3 gap-2">
            <h3 className="font-display font-bold text-navy text-sm">Projets</h3>
            <div className="relative">
              <select
                value={selectedStatus}
                onChange={e => setSelectedStatus(e.target.value)}
                className="appearance-none text-xs bg-slate-50 border border-slate-200 rounded-lg pl-3 pr-7 py-1.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-200 cursor-pointer"
              >
                <option value="">Tous ({kpis.total_projects})</option>
                {STATUS_ORDER.map(key => (
                  <option key={key} value={key}>
                    {STATUS_CONFIG[key].label} ({countByStatus[key] ?? 0})
                  </option>
                ))}
              </select>
              <ChevronDown
                size={12}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
              />
            </div>
          </div>

          {selectedCfg && (
            <p className="text-xs text-slate-400 mb-2">{selectedCfg.desc}</p>
          )}

          {filteredProjects.length === 0 ? (
            <p className="text-xs text-slate-400 py-6 text-center">
              Aucun projet dans cet état.
            </p>
          ) : (
            <div className="space-y-2 max-h-[420px] overflow-y-auto pr-0.5">
              {filteredProjects.map(p => (
                <ProjectCard
                  key={p.id}
                  p={p}
                  onClick={() => nav(`/projet/${p.id}`)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <AlertCircle size={14} className="text-red-500 shrink-0" />
            <h3 className="font-display font-bold text-navy text-sm">Projets à risque</h3>
            <span className="ml-auto text-xs text-slate-400">retard cumulé</span>
          </div>
          <AtRiskList
            items={at_risk_projects}
            onProjectClick={id => nav(`/projet/${id}`)}
          />
        </div>
      </div>
    </div>
  );
}
