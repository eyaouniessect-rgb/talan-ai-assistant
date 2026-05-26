import { useState, useEffect } from "react";
import { ArrowDown, ArrowUp, Minus, ChevronLeft, ChevronRight, RefreshCw, Pencil, Check, X } from "lucide-react";
import clsx from "clsx";
import { getProjectStories } from "../../../api/pipeline";

function tierBadge(rank, total) {
  const ratio = rank / total;
  if (ratio <= 0.25) return "bg-red-100   text-red-700   border border-red-200";
  if (ratio <= 0.50) return "bg-amber-100 text-amber-700 border border-amber-200";
  if (ratio <= 0.75) return "bg-blue-100  text-blue-700  border border-blue-200";
  return                    "bg-slate-100 text-slate-500 border border-slate-200";
}

function rankIcon(rank, total) {
  if (rank <= Math.ceil(total * 0.25))
    return <ArrowUp   size={13} className="text-red-500 shrink-0" />;
  if (rank >= Math.floor(total * 0.75))
    return <ArrowDown size={13} className="text-slate-400 shrink-0" />;
  return  <Minus     size={13} className="text-amber-500 shrink-0" />;
}

function ScoreBar({ score, max }) {
  const pct = max > 0 ? Math.round((score / max) * 100) : 0;
  const color =
    pct >= 75 ? "bg-red-400"   :
    pct >= 45 ? "bg-amber-400" :
    pct >= 15 ? "bg-blue-400"  : "bg-slate-300";
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={clsx("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-slate-400 w-6 text-right shrink-0">{pct}%</span>
    </div>
  );
}

// Trie par priority_score décroissant et réassigne final_rank
function sortAndRank(list) {
  return [...list]
    .sort((a, b) => b.priority_score - a.priority_score)
    .map((r, i) => ({ ...r, final_rank: i + 1 }));
}

export default function PriorisationSection({ aiOutput, projectId, criticalPath = [], onRerun }) {
  const criticalSet = new Set(criticalPath.map(String));

  const [rows,       setRows]      = useState([]);
  const [storyMap,   setStoryMap]  = useState({});
  const [userIdMap,  setUserIdMap] = useState({});
  const [loading,    setLoading]   = useState(true);
  const [editingId,  setEditingId] = useState(null);
  const [editValue,  setEditValue] = useState("");
  const [page,       setPage]      = useState(1);
  const [rerunning,  setRerunning] = useState(false);
  const [rerunError, setRerunError] = useState(null);

  const PAGE_SIZE = 5;

  useEffect(() => {
    const priorities = aiOutput?.priorities ?? [];
    setRows(sortAndRank(priorities));
  }, [aiOutput]);

  useEffect(() => {
    if (!projectId) { setLoading(false); return; }
    getProjectStories(projectId)
      .then(stories => {
        const map = {};
        for (const s of stories) map[s.db_id] = s;
        setStoryMap(map);
        const sorted = [...stories].sort((a, b) => a.db_id - b.db_id);
        setUserIdMap(Object.fromEntries(sorted.map((s, i) => [s.db_id, i + 1])));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [projectId]);

  const startEdit = (story_id, current) => { setEditingId(story_id); setEditValue(String(current)); };
  const cancelEdit = () => { setEditingId(null); setEditValue(""); };
  const confirmEdit = (story_id) => {
    const newScore = parseInt(editValue, 10);
    if (isNaN(newScore) || newScore < 0) { cancelEdit(); return; }
    setRows(prev => sortAndRank(prev.map(r => r.story_id === story_id ? { ...r, priority_score: newScore } : r)));
    setPage(1);
    setEditingId(null);
    setEditValue("");
  };
  const handleKeyDown = (e, story_id) => {
    if (e.key === "Enter")  confirmEdit(story_id);
    if (e.key === "Escape") cancelEdit();
  };

  const handleRerun = async () => {
    if (!onRerun) return;
    setRerunning(true);
    setRerunError(null);
    try {
      const result = await onRerun();
      if (result?.priorities) setRows(sortAndRank(result.priorities));
    } catch (e) {
      setRerunError(e?.response?.data?.detail ?? "Erreur lors du recalcul.");
    } finally {
      setRerunning(false);
    }
  };

  if (!rows.length)
    return <p className="text-sm text-slate-400 italic text-center py-8">Aucune donnée de priorisation disponible.</p>;

  const total      = rows.length;
  const maxScore   = Math.max(...rows.map(r => r.priority_score ?? 0));
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const pageRows   = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="space-y-4">
      {/* Barre supérieure : stat + bouton Relancer */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="inline-flex bg-slate-50 border border-slate-200 rounded-xl px-5 py-3 text-center">
          <div>
            <div className="font-bold text-lg text-navy">{total}</div>
            <div className="text-xs text-slate-400 mt-0.5">Stories</div>
          </div>
        </div>

        {onRerun && (
          <button
            onClick={handleRerun}
            disabled={rerunning}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 bg-white text-slate-600 hover:border-navy hover:text-navy hover:bg-slate-50 text-xs font-medium transition-colors disabled:opacity-50"
          >
            <RefreshCw size={13} className={rerunning ? "animate-spin" : ""} />
            {rerunning ? "Recalcul…" : "Relancer la priorisation"}
          </button>
        )}

        {rerunError && (
          <span className="text-xs text-red-500 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5">
            {rerunError}
          </span>
        )}
      </div>

      {/* Tableau */}
      <div className="rounded-xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-[48px_48px_32px_1fr_72px_180px] gap-2 px-4 py-2.5 bg-slate-50 border-b border-slate-200 text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
          <span>ID</span>
          <span>Rang</span>
          <span></span>
          <span>Story</span>
          <span className="text-center">Points</span>
          <span>Score priorité</span>
        </div>

        {/* Rows */}
        <div className="divide-y divide-slate-100 bg-white">
          {pageRows.map(({ story_id, priority_score, final_rank }) => {
            const story     = storyMap[story_id];
            const pts       = story?.story_points;
            const isEditing = editingId === story_id;

            return (
              <div
                key={story_id}
                className="grid grid-cols-[48px_48px_32px_1fr_72px_180px] gap-2 px-4 py-3 items-center hover:bg-slate-50 transition-colors"
              >
                {/* ID utilisateur cohérent entre phases */}
                <span className="text-xs font-mono font-semibold text-slate-500">
                  #{userIdMap[story_id] ?? "—"}
                </span>

                {/* Rang de priorité */}
                <span className={clsx("text-xs font-bold px-2 py-0.5 rounded-full w-fit", tierBadge(final_rank, total))}>
                  {final_rank}
                </span>

                {/* Icône tendance */}
                <span>{rankIcon(final_rank, total)}</span>

                {/* Titre + vrai DB ID */}
                <div className="min-w-0">
                  {loading ? (
                    <div className="h-3 bg-slate-100 rounded w-3/4 animate-pulse" />
                  ) : story ? (
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        {criticalSet.has(String(story_id)) && (
                          <span className="shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-500 text-white uppercase tracking-wide">
                            Critique
                          </span>
                        )}
                        <p className="text-sm text-slate-800 font-medium leading-snug">
                          {story.jira_issue_key && (
                            <span className="font-mono text-cyan-700 mr-1.5">{story.jira_issue_key}</span>
                          )}
                          {story.title}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400 italic">Story #{story_id}</span>
                  )}
                </div>

                {/* Story points */}
                <div className="text-center">
                  {pts != null ? (
                    <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-slate-100 text-slate-600">
                      {pts} sp
                    </span>
                  ) : (
                    <span className="text-xs text-slate-300">—</span>
                  )}
                </div>

                {/* Score — affichage ou édition inline */}
                <div className="space-y-1">
                  {isEditing ? (
                    <div className="flex items-center gap-1.5">
                      <input
                        autoFocus
                        type="number"
                        min="0"
                        value={editValue}
                        onChange={e => setEditValue(e.target.value)}
                        onKeyDown={e => handleKeyDown(e, story_id)}
                        className="w-16 border border-navy/40 rounded-md px-2 py-0.5 text-xs font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-navy/30"
                      />
                      <button onClick={() => confirmEdit(story_id)} className="p-1 rounded hover:bg-green-50 text-green-600"><Check size={13} /></button>
                      <button onClick={cancelEdit} className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500"><X size={13} /></button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-semibold text-slate-700">{priority_score}</span>
                      <button
                        onClick={() => startEdit(story_id, priority_score)}
                        className="flex items-center gap-1 px-2 py-0.5 rounded-md border border-slate-300 bg-white text-slate-500 hover:border-navy hover:text-navy hover:bg-slate-50 transition-colors text-[11px] font-medium"
                      >
                        <Pencil size={10} /> Modifier
                      </button>
                    </div>
                  )}
                  {!isEditing && <ScoreBar score={priority_score} max={maxScore} />}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-1">
          <span className="text-xs text-slate-400">
            {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} sur {total}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => p - 1)}
              disabled={page === 1}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-navy disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
              <button
                key={p}
                onClick={() => setPage(p)}
                className={clsx(
                  "w-7 h-7 rounded-lg text-xs font-semibold border transition-colors",
                  p === page
                    ? "bg-navy text-white border-navy"
                    : "border-slate-200 text-slate-500 hover:border-navy hover:text-navy"
                )}
              >
                {p}
              </button>
            ))}
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={page === totalPages}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-navy disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
