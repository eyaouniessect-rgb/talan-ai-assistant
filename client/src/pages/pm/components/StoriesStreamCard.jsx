import { useEffect, useRef, useState } from "react";
import {
  Loader, CheckCircle, AlertTriangle, RotateCcw,
  Zap, BookOpen, Star, Search, ChevronRight,
} from "lucide-react";

// ── Icône par tool ─────────────────────────────────────────────
const TOOL_ICON = {
  generate_stories_for_epic:      { icon: BookOpen, color: "text-violet-500", bg: "bg-violet-50" },
  estimate_story_points:          { icon: Star,     color: "text-blue-500",   bg: "bg-blue-50"   },
  generate_acceptance_criteria:   { icon: CheckCircle, color: "text-green-500", bg: "bg-green-50" },
  review_coverage:                { icon: Search,   color: "text-amber-500",  bg: "bg-amber-50"  },
};

const TOOL_LABEL = {
  generate_stories_for_epic:      "Génération des stories",
  estimate_story_points:          "Estimation story points",
  generate_acceptance_criteria:   "Critères d'acceptation",
  review_coverage:                "Revue de couverture",
};

// ── Ligne de log ───────────────────────────────────────────────
function LogEntry({ entry, isLast }) {
  const { type, epic_title, epic_idx, tool, label, gaps, thinking,
          missing_features, stories_count, nb_epics, total_stories } = entry;

  // epic_start
  if (type === "epic_start") {
    return (
      <div className="flex items-center gap-2 py-1.5">
        <Zap size={13} className="text-navy shrink-0" />
        <span className="text-xs font-semibold text-navy">
          Epic {(epic_idx ?? 0) + 1}/{nb_epics ?? "?"} —{" "}
          <span className="font-normal text-slate-600 truncate max-w-[260px] inline-block align-bottom">
            {epic_title}
          </span>
        </span>
      </div>
    );
  }

  // tool_start
  if (type === "tool_start") {
    const meta = TOOL_ICON[tool] ?? { icon: Loader, color: "text-slate-400", bg: "bg-slate-50" };
    const Icon = meta.icon;
    return (
      <div className={`flex items-center gap-2 py-1 pl-4`}>
        {isLast
          ? <Loader size={12} className={`${meta.color} animate-spin shrink-0`} />
          : <Icon  size={12} className={`${meta.color} shrink-0`} />
        }
        <span className={`text-xs ${isLast ? meta.color : "text-slate-400"}`}>
          {label ?? TOOL_LABEL[tool] ?? tool}
          {isLast && <span className="animate-pulse">…</span>}
        </span>
        {!isLast && <CheckCircle size={10} className="text-green-400 ml-auto shrink-0" />}
      </div>
    );
  }

  // gap_detected
  if (type === "gap_detected") {
    return (
      <div className="my-1.5 mx-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 space-y-1.5">
        <div className="flex items-center gap-1.5">
          <AlertTriangle size={12} className="text-amber-500 shrink-0" />
          <span className="text-xs font-semibold text-amber-700">
            Gaps détectés — Epic «\u00a0{epic_title}\u00a0»
          </span>
        </div>
        <div className="flex flex-wrap gap-1">
          {(gaps ?? []).map((g, i) => (
            <span key={i} className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
              {g}
            </span>
          ))}
        </div>
        {thinking && (
          <p className="text-xs text-amber-600 italic leading-relaxed">{thinking}</p>
        )}
      </div>
    );
  }

  // retry_start
  if (type === "retry_start") {
    return (
      <div className="flex items-start gap-2 py-1 pl-4">
        <RotateCcw size={12} className="text-violet-500 mt-0.5 shrink-0 animate-spin" />
        <div className="space-y-0.5">
          <span className="text-xs font-medium text-violet-600">
            Régénération ciblée
          </span>
          {missing_features?.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {missing_features.slice(0, 4).map((f, i) => (
                <span key={i} className="text-xs bg-violet-50 text-violet-600 px-1.5 py-0.5 rounded">
                  + {f}
                </span>
              ))}
              {missing_features.length > 4 && (
                <span className="text-xs text-violet-400">+{missing_features.length - 4} autres</span>
              )}
            </div>
          )}
          {thinking && (
            <p className="text-xs text-violet-500 italic">{thinking}</p>
          )}
        </div>
      </div>
    );
  }

  // coverage_ok
  if (type === "coverage_ok") {
    return (
      <div className="flex items-center gap-2 py-1 pl-4">
        <CheckCircle size={12} className="text-green-500 shrink-0" />
        <span className="text-xs text-green-600">Couverture validée</span>
      </div>
    );
  }

  // epic_done
  if (type === "epic_done") {
    return (
      <div className="flex items-center gap-2 py-1 pl-4">
        <CheckCircle size={12} className="text-green-500 shrink-0" />
        <span className="text-xs text-green-700 font-medium">
          {stories_count} stories générées ✓
        </span>
      </div>
    );
  }

  // done
  if (type === "done") {
    return (
      <div className="flex items-center gap-2 py-2 mt-1 border-t border-green-100">
        <CheckCircle size={14} className="text-green-500 shrink-0" />
        <span className="text-sm font-semibold text-green-700">
          Génération terminée — {total_stories} stories pour {nb_epics} epic(s)
        </span>
      </div>
    );
  }

  return null;
}

// ── Composant principal ────────────────────────────────────────
export default function StoriesStreamCard({ projectId }) {
  const [logs, setLogs]         = useState([]);
  const [thinking, setThinking] = useState("");  // tokens LLM en cours
  const [done, setDone]         = useState(false);
  const [error, setError]       = useState(null);
  const [epicProgress, setEpicProgress] = useState({ current: 0, total: 0 });

  const bottomRef  = useRef(null);
  const esRef      = useRef(null);
  const thinkBuf   = useRef("");    // buffer tokens LLM
  const thinkTimer = useRef(null);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token || !projectId) return;

    const url = `http://localhost:8000/pipeline/${projectId}/stories/stream?token=${encodeURIComponent(token)}`;
    const es  = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      let evt;
      try { evt = JSON.parse(e.data); } catch { return; }

      const { type } = evt;

      if (type === "heartbeat") return;

      // Tokens LLM → affichage progressif dans le bandeau "Réflexion"
      if (type === "llm_token") {
        thinkBuf.current += evt.token ?? "";
        if (thinkTimer.current) clearTimeout(thinkTimer.current);
        // Afficher les 200 derniers chars du buffer
        setThinking(thinkBuf.current.slice(-200));
        // Effacer le buffer après 4s d'inactivité (l'IA a fini de réfléchir)
        thinkTimer.current = setTimeout(() => {
          thinkBuf.current = "";
          setThinking("");
        }, 4000);
        return;
      }

      // Progression epics
      if (type === "epic_start") {
        setEpicProgress({ current: (evt.epic_idx ?? 0) + 1, total: evt.nb_epics ?? 0 });
      }
      if (type === "done") {
        setDone(true);
        es.close();
      }
      if (type === "error") {
        setError(evt.message ?? "Erreur inconnue");
        es.close();
      }

      // Ajouter l'entrée dans le log (sauf tokens)
      if (!["heartbeat", "llm_token"].includes(type)) {
        setLogs((prev) => [...prev, evt]);
      }
    };

    es.onerror = () => {
      if (!done) setError("Connexion SSE interrompue.");
      es.close();
    };

    return () => {
      es.close();
      if (thinkTimer.current) clearTimeout(thinkTimer.current);
    };
  }, [projectId]); // eslint-disable-line

  // Auto-scroll vers le bas
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, thinking]);

  const progressPct = epicProgress.total > 0
    ? Math.round((epicProgress.current / epicProgress.total) * 100)
    : 0;

  return (
    <div className="card p-5 border-2 border-violet-200 space-y-3">
      {/* En-tête */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {done
            ? <CheckCircle size={16} className="text-green-500" />
            : <Loader size={16} className="text-violet-500 animate-spin" />
          }
          <span className="text-sm font-semibold text-navy">
            {done ? "User Stories générées" : "Génération des User Stories en cours…"}
          </span>
        </div>
        {epicProgress.total > 0 && (
          <span className="text-xs text-slate-400">
            Epic {epicProgress.current}/{epicProgress.total}
          </span>
        )}
      </div>

      {/* Barre de progression */}
      {epicProgress.total > 0 && (
        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-violet-400 rounded-full transition-all duration-500"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      )}

      {/* Journal des événements */}
      <div className="bg-slate-50 rounded-xl border border-slate-200 p-3 max-h-80 overflow-y-auto space-y-0.5">
        {logs.length === 0 && !error && (
          <div className="flex items-center gap-2 py-2 text-xs text-slate-400">
            <Loader size={12} className="animate-spin" /> Connexion au flux…
          </div>
        )}

        {logs.map((entry, i) => (
          <LogEntry key={i} entry={entry} isLast={i === logs.length - 1 && !done} />
        ))}

        {error && (
          <div className="flex items-center gap-2 py-2 text-xs text-red-600">
            <AlertTriangle size={12} className="shrink-0" /> {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Bandeau "Réflexion LLM" (tokens en streaming) */}
      {thinking && !done && (
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
          <div className="flex items-center gap-1.5 mb-1">
            <ChevronRight size={11} className="text-slate-400" />
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">
              Réflexion LLM
            </span>
            <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse ml-auto" />
          </div>
          <p className="text-xs text-slate-500 font-mono leading-relaxed whitespace-pre-wrap break-all">
            {thinking}
            <span className="inline-block w-1.5 h-3.5 bg-violet-400 ml-0.5 animate-pulse align-middle" />
          </p>
        </div>
      )}
    </div>
  );
}
