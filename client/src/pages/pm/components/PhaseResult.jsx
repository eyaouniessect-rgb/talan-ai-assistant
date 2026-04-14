import { CheckCircle, FileText, Eye, ArrowRight, ShieldAlert, ShieldCheck, AlertTriangle } from "lucide-react";
import clsx from "clsx";

// ── Rendu du rapport de sécurité ──────────────────────────────
const SEVERITY_STYLE = {
  critical: { bg: "bg-red-50",    border: "border-red-300",    text: "text-red-700",    badge: "bg-red-100 text-red-700"    },
  high:     { bg: "bg-orange-50", border: "border-orange-300", text: "text-orange-700", badge: "bg-orange-100 text-orange-700" },
  medium:   { bg: "bg-amber-50",  border: "border-amber-300",  text: "text-amber-700",  badge: "bg-amber-100 text-amber-700"  },
  low:      { bg: "bg-yellow-50", border: "border-yellow-200", text: "text-yellow-700", badge: "bg-yellow-100 text-yellow-700" },
};

const THREAT_TYPE_LABEL = {
  prompt_injection: "Prompt Injection",
  sql_injection:    "SQL Injection",
  code_injection:   "Code Injection",
  mcp_injection:    "MCP / Tool Injection",
  double_extension: "Double Extension",
};

function SecurityReport({ scan }) {
  if (!scan) return null;

  if (scan.is_safe)
    return (
      <div className="flex items-center gap-2 bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 text-sm">
        <ShieldCheck size={15} className="shrink-0" />
        <span>Analyse de sécurité réussie — aucune menace détectée.</span>
      </div>
    );

  const style = SEVERITY_STYLE[scan.severity] ?? SEVERITY_STYLE.medium;

  return (
    <div className={clsx("rounded-xl border-2 overflow-hidden", style.border)}>
      {/* Header */}
      <div className={clsx("flex items-center gap-2 px-4 py-3", style.bg)}>
        <ShieldAlert size={16} className={clsx("shrink-0", style.text)} />
        <span className={clsx("text-sm font-semibold", style.text)}>
          {scan.blocked
            ? `⛔ Contenu bloqué — ${scan.threat_count} menace${scan.threat_count > 1 ? "s" : ""} détectée${scan.threat_count > 1 ? "s" : ""}`
            : `⚠ ${scan.threat_count} menace${scan.threat_count > 1 ? "s" : ""} détectée${scan.threat_count > 1 ? "s" : ""}`}
        </span>
        <span className={clsx("ml-auto text-xs font-bold px-2 py-0.5 rounded-full uppercase", style.badge)}>
          {scan.severity}
        </span>
      </div>

      {/* Threats list */}
      <div className="divide-y divide-slate-100 bg-white">
        {scan.threats.map((t, i) => {
          const ts = SEVERITY_STYLE[t.severity] ?? SEVERITY_STYLE.medium;
          return (
            <div key={i} className="px-4 py-3 space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <AlertTriangle size={13} className={clsx("shrink-0", ts.text)} />
                <span className="text-xs font-semibold text-slate-700">
                  {THREAT_TYPE_LABEL[t.type] ?? t.type}
                </span>
                <code className="text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-mono">{t.pattern}</code>
                <span className={clsx("ml-auto text-xs px-2 py-0.5 rounded-full font-medium", ts.badge)}>
                  {t.severity}
                </span>
              </div>
              <p className="text-xs text-slate-500">{t.description}</p>
              {t.excerpt && (
                <code className="block text-xs bg-slate-50 border border-slate-200 rounded px-2 py-1 text-slate-600 truncate font-mono">
                  {t.excerpt}
                </code>
              )}
            </div>
          );
        })}
      </div>

      {scan.blocked && (
        <div className="px-4 py-2 bg-red-50 border-t border-red-200">
          <p className="text-xs text-red-600 font-medium">
            Ce document contient des menaces critiques. Rejetez cette phase et contactez l'auteur du fichier.
          </p>
        </div>
      )}
    </div>
  );
}

export default function PhaseResult({ phaseId, aiOutput }) {
  if (!aiOutput && phaseId !== "extract")
    return <p className="text-slate-400 text-sm italic">Aucun résultat disponible pour cette phase.</p>;
  if (!aiOutput) aiOutput = {};

  if (phaseId === "extract") {
    const { filename, file_size, pages_est, chars, preview, security_scan } = aiOutput;

    if (!pages_est && !chars)
      return (
        <div className="space-y-3">
          <div className="flex items-center gap-2 bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 text-sm">
            <CheckCircle size={15} className="shrink-0" />
            Extraction réussie — détails non disponibles (exécution précédente).
          </div>
          <SecurityReport scan={security_scan} />
        </div>
      );

    return (
      <div className="space-y-4">
        {/* Rapport de sécurité en premier si des menaces existent */}
        <SecurityReport scan={security_scan} />

        <div className="grid grid-cols-3 gap-3">
          {[
            ["Pages estimées", pages_est ?? "—"],
            ["Caractères",     chars ? chars.toLocaleString("fr-FR") : "—"],
            ["Taille fichier", file_size ? `${(file_size / 1024).toFixed(0)} KB` : "—"],
          ].map(([k, v]) => (
            <div key={k} className="bg-slate-50 rounded-xl p-3 text-center">
              <div className="font-display font-bold text-navy text-lg">{v}</div>
              <div className="text-xs text-slate-400 mt-0.5">{k}</div>
            </div>
          ))}
        </div>
        {filename && (
          <div className="flex items-center gap-2 text-sm text-slate-600 bg-slate-50 rounded-xl px-3 py-2">
            <FileText size={14} className="text-cyan shrink-0" />
            <span className="font-medium truncate">{filename}</span>
          </div>
        )}
        {preview && (
          <div>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              <Eye size={12} /> Texte extrait (aperçu)
            </div>
            <pre className="text-xs text-slate-700 bg-slate-50 border border-slate-200 rounded-xl p-4
                            overflow-auto max-h-64 whitespace-pre-wrap leading-relaxed font-mono">
              {preview}
            </pre>
            {chars > 1500 && (
              <p className="text-xs text-slate-400 mt-1.5 text-right">
                ... {(chars - 1500).toLocaleString("fr-FR")} caractères supplémentaires
              </p>
            )}
          </div>
        )}
      </div>
    );
  }

  if (phaseId === "epics") {
    const epics = aiOutput.epics ?? [];
    if (!epics.length) return <p className="text-slate-400 text-sm italic">Aucun epic généré.</p>;
    return (
      <div className="space-y-2">
        {epics.map((epic, i) => (
          <div key={i} className="flex items-start gap-3 p-3 bg-slate-50 rounded-xl">
            <div className="w-6 h-6 bg-navy text-white rounded-lg flex items-center justify-center text-xs font-bold shrink-0">
              {i + 1}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-navy">{epic.title}</div>
              {epic.description && <div className="text-xs text-slate-500 mt-0.5">{epic.description}</div>}
              {epic.splitting_strategy && (
                <div className="text-xs text-slate-400 mt-1">
                  Stratégie : <span className="text-cyan font-medium">{epic.splitting_strategy.replace(/_/g, " ")}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (phaseId === "stories") {
    const stories = aiOutput.stories ?? [];
    if (!stories.length) return <p className="text-slate-400 text-sm italic">Aucune story générée.</p>;
    return (
      <div className="space-y-2">
        {stories.map((s, i) => (
          <div key={i} className="p-3 bg-slate-50 rounded-xl">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm text-slate-700">{s.title}</p>
              {s.story_points && (
                <span className="text-xs bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full shrink-0">
                  {s.story_points} pts
                </span>
              )}
            </div>
            {(s.epic_id || s.acceptance_criteria?.length > 0) && (
              <div className="flex items-center gap-3 mt-1.5">
                {s.epic_id && <span className="text-xs text-slate-400">Epic #{s.epic_id}</span>}
                {s.acceptance_criteria?.length > 0 && (
                  <span className="text-xs text-green-600">· {s.acceptance_criteria.length} critères</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (phaseId === "cpm") {
    const { project_duration, critical_tasks, max_slack, critical_path } = aiOutput;
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-3">
          {[
            ["Durée projet",     project_duration != null ? `${project_duration}j` : "—", "text-navy"],
            ["Tâches critiques", critical_tasks ?? "—",                                    "text-red-600"],
            ["Marge max",        max_slack != null ? `${max_slack}j` : "—",               "text-green-600"],
          ].map(([k, v, cls]) => (
            <div key={k} className="bg-slate-50 rounded-xl p-3 text-center">
              <div className={clsx("font-display font-bold text-xl", cls)}>{v}</div>
              <div className="text-xs text-slate-400">{k}</div>
            </div>
          ))}
        </div>
        {critical_path?.length > 0 && (
          <div>
            <p className="text-xs font-medium text-slate-500 mb-2">Chemin critique :</p>
            <div className="flex flex-wrap items-center gap-1.5">
              {critical_path.map((t, i) => (
                <span key={i} className="flex items-center gap-1">
                  <span className="text-xs bg-red-50 text-red-700 px-2 py-0.5 rounded-full">{t}</span>
                  {i < critical_path.length - 1 && <ArrowRight size={10} className="text-slate-300" />}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <pre className="text-xs text-slate-600 bg-slate-50 p-3 rounded-xl overflow-auto max-h-64 whitespace-pre-wrap">
      {JSON.stringify(aiOutput, null, 2)}
    </pre>
  );
}
