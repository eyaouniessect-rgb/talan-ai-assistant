import { useState, useEffect } from "react";
import { CheckCircle, FileText, Eye, ArrowRight, ShieldAlert, ShieldCheck,
         AlertTriangle, Component, AlertCircle, ShieldOff,
         ChevronDown, ChevronRight, Pencil, Trash2, X, Save, PlayCircle,
         Users, Wrench, Layers, Plus } from "lucide-react";
import clsx from "clsx";
import { updateStory, deleteStory, getProjectStories, getProjectEpics, addEpic, updateEpic, deleteEpic, addStory } from "../../../api/pipeline";

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
  const cleaned = scan.was_cleaned === true;

  return (
    <div className={clsx("rounded-xl border-2 overflow-hidden", cleaned ? "border-amber-300" : style.border)}>
      {/* Header */}
      <div className={clsx("flex items-center gap-2 px-4 py-3", cleaned ? "bg-amber-50" : style.bg)}>
        {cleaned
          ? <ShieldOff size={16} className="shrink-0 text-amber-600" />
          : <ShieldAlert size={16} className={clsx("shrink-0", style.text)} />
        }
        <span className={clsx("text-sm font-semibold", cleaned ? "text-amber-700" : style.text)}>
          {cleaned
            ? `Document nettoyé — ${scan.threat_count} pattern${scan.threat_count > 1 ? "s" : ""} supprimé${scan.threat_count > 1 ? "s" : ""}`
            : `⛔ Contenu bloqué — ${scan.threat_count} menace${scan.threat_count > 1 ? "s" : ""} détectée${scan.threat_count > 1 ? "s" : ""}`
          }
        </span>
        <span className={clsx(
          "ml-auto text-xs font-bold px-2 py-0.5 rounded-full uppercase",
          cleaned ? "bg-amber-100 text-amber-700" : style.badge
        )}>
          {cleaned ? "nettoyé" : scan.severity}
        </span>
      </div>

      {/* Threats list */}
      <div className="divide-y divide-slate-100 bg-white">
        {scan.threats.map((t, i) => {
          const ts = SEVERITY_STYLE[t.severity] ?? SEVERITY_STYLE.medium;
          return (
            <div key={i} className={clsx("px-4 py-3 space-y-1", cleaned && "opacity-75")}>
              <div className="flex items-center gap-2 flex-wrap">
                <AlertTriangle size={13} className={clsx("shrink-0", ts.text)} />
                <span className="text-xs font-semibold text-slate-700">
                  {THREAT_TYPE_LABEL[t.type] ?? t.type}
                </span>
                <code className="text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-mono">{t.pattern}</code>
                <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", ts.badge)}>
                  {t.severity}
                </span>
                {cleaned && (
                  <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium ml-auto">
                    ✓ supprimé
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500">{t.description}</p>
              {t.excerpt && (
                <code className="block text-xs bg-slate-50 border border-slate-200 rounded px-2 py-1 text-slate-500 truncate font-mono line-through decoration-red-300">
                  {t.excerpt}
                </code>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer selon état */}
      {cleaned ? (
        <div className="px-4 py-2 bg-amber-50 border-t border-amber-200">
          <p className="text-xs text-amber-700 font-medium">
            Les patterns d'injection ont été supprimés du texte. Le traitement continue avec le document assaini.
          </p>
        </div>
      ) : scan.blocked ? (
        <div className="px-4 py-2 bg-red-50 border-t border-red-200">
          <p className="text-xs text-red-600 font-medium">
            Ce document contient des menaces critiques. Rejetez cette phase et contactez l'auteur du fichier.
          </p>
        </div>
      ) : null}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// STORIES SECTION — composant dédié
// ══════════════════════════════════════════════════════════════

// Couleurs par splitting_strategy
const STRATEGY_STYLE = {
  by_feature:       "bg-violet-100 text-violet-700 border-violet-200",
  by_user_role:     "bg-blue-100   text-blue-700   border-blue-200",
  by_workflow_step: "bg-amber-100  text-amber-700  border-amber-200",
  by_component:     "bg-green-100  text-green-700  border-green-200",
  by_layer:         "bg-indigo-100 text-indigo-700 border-indigo-200",
};
const strategyStyle = (s) => STRATEGY_STYLE[s] ?? "bg-slate-100 text-slate-600 border-slate-200";
const strategyLabel = (s) => (s ?? "").replace(/_/g, " ");

// Couleur points Fibonacci
const spStyle = (pts) => {
  if (!pts || pts <= 2) return "bg-green-100 text-green-700";
  if (pts <= 5) return "bg-blue-100 text-blue-700";
  if (pts <= 8) return "bg-orange-100 text-orange-700";
  return "bg-red-100 text-red-700";
};

// Normalise acceptance_criteria (string JSON ou tableau)
function parseAC(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  try { return JSON.parse(raw); } catch { return raw ? [raw] : []; }
}

// ── Modal d'édition ────────────────────────────────────────────
function EditModal({ story, onClose, onSaved }) {
  const [title, setTitle]       = useState(story.title ?? "");
  const [desc,  setDesc]        = useState(story.description ?? "");
  const [pts,   setPts]         = useState(story.story_points ?? 3);
  const [ac,    setAC]          = useState(parseAC(story.acceptance_criteria));
  const [saving, setSaving]     = useState(false);
  const [err,    setErr]        = useState(null);

  const handleSave = async () => {
    setSaving(true);
    setErr(null);
    try {
      await updateStory(story.db_id, { title, description: desc, story_points: pts, acceptance_criteria: ac });
      onSaved({ ...story, title, description: desc, story_points: pts, acceptance_criteria: ac });
    } catch (e) {
      setErr(e?.response?.data?.detail ?? "Erreur lors de la sauvegarde.");
    } finally {
      setSaving(false);
    }
  };

  const updateCriterion = (i, val) => setAC(prev => prev.map((c, j) => j === i ? val : c));
  const removeCriterion = (i)      => setAC(prev => prev.filter((_, j) => j !== i));
  const addCriterion    = ()       => ac.length < 3 && setAC(prev => [...prev, ""]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200">
          <span className="text-sm font-semibold text-navy">Modifier la story</span>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* Titre */}
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Titre</label>
            <textarea
              value={title}
              onChange={e => setTitle(e.target.value)}
              rows={2}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 resize-none focus:outline-none focus:ring-2 focus:ring-violet-300"
            />
          </div>

          {/* Description */}
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Description</label>
            <textarea
              value={desc}
              onChange={e => setDesc(e.target.value)}
              rows={3}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-600 resize-none focus:outline-none focus:ring-2 focus:ring-violet-300"
            />
          </div>

          {/* Story points */}
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">
              Story Points
              <span className="font-normal text-slate-400 ml-1">(Fibonacci)</span>
            </label>
            <div className="flex gap-2 flex-wrap">
              {[1, 2, 3, 5, 8, 13].map(v => (
                <button
                  key={v}
                  onClick={() => setPts(v)}
                  className={clsx(
                    "w-9 h-9 rounded-lg text-sm font-semibold border transition-colors",
                    pts === v
                      ? "bg-navy text-white border-navy"
                      : "bg-slate-50 text-slate-600 border-slate-200 hover:border-navy"
                  )}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>

          {/* Critères d'acceptation */}
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">
              Critères d'acceptation ({ac.length}/3)
            </label>
            <div className="space-y-2">
              {ac.map((c, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    value={c}
                    onChange={e => updateCriterion(i, e.target.value)}
                    className="flex-1 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-violet-300"
                  />
                  <button onClick={() => removeCriterion(i)} className="text-slate-300 hover:text-red-400">
                    <X size={14} />
                  </button>
                </div>
              ))}
              {ac.length < 3 && (
                <button
                  onClick={addCriterion}
                  className="text-xs text-violet-600 hover:underline"
                >
                  + Ajouter un critère
                </button>
              )}
            </div>
          </div>

          {err && <p className="text-xs text-red-600">{err}</p>}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-slate-200">
          <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-700 px-3 py-1.5">
            Annuler
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !title.trim()}
            className="flex items-center gap-1.5 bg-navy text-white text-xs font-medium px-4 py-1.5 rounded-lg disabled:opacity-50"
          >
            <Save size={12} /> {saving ? "Sauvegarde…" : "Sauvegarder"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Modal d'ajout d'une story ──────────────────────────────────
function AddStoryModal({ projectId, epicIdx, epicTitle, onClose, onAdded }) {
  const [title,   setTitle]   = useState("");
  const [desc,    setDesc]    = useState("");
  const [pts,     setPts]     = useState(3);
  const [ac,      setAC]      = useState([""]);
  const [saving,  setSaving]  = useState(false);
  const [err,     setErr]     = useState(null);

  const handleSave = async () => {
    if (!title.trim()) return;
    setSaving(true);
    setErr(null);
    try {
      const created = await addStory(projectId, {
        epic_idx:            epicIdx,
        title:               title.trim(),
        description:         desc.trim(),
        story_points:        pts,
        acceptance_criteria: ac.filter(c => c.trim()),
      });
      onAdded({ ...created, epic_id: epicIdx });
    } catch (e) {
      setErr(e?.response?.data?.detail ?? "Erreur lors de la création.");
    } finally {
      setSaving(false);
    }
  };

  const updateAC  = (i, v) => setAC(prev => prev.map((c, j) => j === i ? v : c));
  const removeAC  = (i)    => setAC(prev => prev.filter((_, j) => j !== i));
  const addAC     = ()     => ac.length < 5 && setAC(prev => [...prev, ""]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200">
          <div>
            <span className="text-sm font-semibold text-navy">Ajouter une story</span>
            <p className="text-xs text-slate-400 mt-0.5">{epicTitle}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={16} /></button>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* Titre */}
          <div>
            <label className="text-xs font-semibold text-slate-600 mb-1 block">Titre *</label>
            <textarea
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="En tant que ..., je veux ... afin de ..."
              rows={2}
              className="input w-full resize-none text-sm"
            />
          </div>

          {/* Description */}
          <div>
            <label className="text-xs font-semibold text-slate-600 mb-1 block">Description</label>
            <textarea
              value={desc}
              onChange={e => setDesc(e.target.value)}
              rows={3}
              className="input w-full resize-none text-sm"
            />
          </div>

          {/* Story points */}
          <div>
            <label className="text-xs font-semibold text-slate-600 mb-1 block">
              Story Points
              <span className="font-normal text-slate-400 ml-1">(Fibonacci : 1 2 3 5 8 13)</span>
            </label>
            <div className="flex gap-2 flex-wrap">
              {[1, 2, 3, 5, 8, 13].map(n => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setPts(n)}
                  className={clsx(
                    "w-9 h-9 rounded-lg text-sm font-semibold border transition-colors",
                    pts === n
                      ? "bg-navy text-white border-navy"
                      : "border-slate-200 text-slate-600 hover:border-navy"
                  )}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* Critères d'acceptation */}
          <div>
            <label className="text-xs font-semibold text-slate-600 mb-1 block">
              Critères d'acceptation
            </label>
            <div className="space-y-2">
              {ac.map((c, i) => (
                <div key={i} className="flex gap-2 items-start">
                  <input
                    value={c}
                    onChange={e => updateAC(i, e.target.value)}
                    placeholder={`Critère ${i + 1}`}
                    className="input flex-1 text-sm"
                  />
                  <button onClick={() => removeAC(i)} className="p-1.5 text-slate-400 hover:text-red-500 mt-0.5">
                    <X size={13} />
                  </button>
                </div>
              ))}
              {ac.length < 5 && (
                <button onClick={addAC} className="text-xs text-navy hover:underline flex items-center gap-1">
                  <Plus size={11} /> Ajouter un critère
                </button>
              )}
            </div>
          </div>

          {err && <p className="text-xs text-red-500 bg-red-50 rounded-lg px-3 py-2">{err}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-slate-200">
          <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-700 px-3 py-1.5">
            Annuler
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !title.trim()}
            className="flex items-center gap-1.5 bg-navy text-white text-xs font-medium px-4 py-1.5 rounded-lg disabled:opacity-50"
          >
            <Plus size={12} /> {saving ? "Création…" : "Créer la story"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Card d'une story ───────────────────────────────────────────
function StoryCard({ story: initialStory, onDeleted }) {
  const [story,      setStory]      = useState(initialStory);
  const [open,       setOpen]       = useState(false);   // critères collapsed
  const [editing,    setEditing]    = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting,   setDeleting]   = useState(false);

  const ac = parseAC(story.acceptance_criteria);

  const handleDelete = async () => {
    if (!story.db_id) return;
    setDeleting(true);
    try {
      await deleteStory(story.db_id);
      onDeleted(story.db_id);
    } catch {
      setDeleting(false);
      setConfirmDel(false);
    }
  };

  return (
    <>
      {editing && story.db_id && (
        <EditModal
          story={story}
          onClose={() => setEditing(false)}
          onSaved={(updated) => { setStory(updated); setEditing(false); }}
        />
      )}
      <div className="px-4 py-3 space-y-2">
        {/* Ligne 1 : titre + points */}
        <div className="flex items-start gap-2">
          <p className="text-sm text-slate-800 flex-1 leading-snug font-medium">{story.title}</p>
          <span className={`text-xs px-2 py-0.5 rounded-full font-semibold shrink-0 ${spStyle(story.story_points)}`}>
            {story.story_points ?? "?"} pts
          </span>
        </div>

        {/* Ligne 2 : badge stratégie + actions */}
        <div className="flex items-center gap-2 flex-wrap">
          {story.splitting_strategy && (
            <span className={clsx(
              "text-xs px-2 py-0.5 rounded-full border font-medium",
              strategyStyle(story.splitting_strategy)
            )}>
              {strategyLabel(story.splitting_strategy)}
            </span>
          )}
          <div className="ml-auto flex items-center gap-1">
            {story.db_id && (
              <>
                <button
                  onClick={() => setEditing(true)}
                  className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-navy transition-colors"
                  title="Modifier"
                >
                  <Pencil size={12} />
                </button>
                {!confirmDel ? (
                  <button
                    onClick={() => setConfirmDel(true)}
                    className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors"
                    title="Supprimer"
                  >
                    <Trash2 size={12} />
                  </button>
                ) : (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-red-500">Supprimer ?</span>
                    <button
                      onClick={handleDelete}
                      disabled={deleting}
                      className="text-xs bg-red-500 text-white px-2 py-0.5 rounded font-medium hover:bg-red-600 disabled:opacity-50"
                    >
                      Oui
                    </button>
                    <button
                      onClick={() => setConfirmDel(false)}
                      className="text-xs text-slate-500 hover:text-slate-700 px-1"
                    >
                      Non
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Description */}
        {story.description && (
          <p className="text-xs text-slate-500 leading-relaxed">{story.description}</p>
        )}

        {/* Critères collapsibles */}
        {ac.length > 0 && (
          <div>
            <button
              onClick={() => setOpen(o => !o)}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 transition-colors"
            >
              {open
                ? <ChevronDown size={12} className="text-green-500" />
                : <ChevronRight size={12} className="text-slate-400" />
              }
              <span className={clsx("font-medium", open ? "text-green-600" : "text-slate-500")}>
                {ac.length} critère{ac.length > 1 ? "s" : ""} d'acceptation
              </span>
            </button>
            {open && (
              <ul className="mt-1.5 space-y-1 pl-1 border-l-2 border-green-100 ml-1">
                {ac.map((criterion, ci) => (
                  <li key={ci} className="flex items-start gap-1.5 text-xs text-slate-600 pl-2">
                    <span className="text-green-500 mt-0.5 shrink-0">✓</span>
                    <span className="leading-relaxed">{criterion}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {ac.length === 0 && (
          <span className="text-xs text-slate-300 italic">Aucun critère</span>
        )}
      </div>
    </>
  );
}

// ── Bandeau de review par epic ─────────────────────────────────
function EpicReviewBanner({ review }) {
  const [open, setOpen] = useState(false);
  if (!review) return null;
  const { coverage_ok, gaps = [], scope_creep_issues = [], quality_issues = [], suggestions = [] } = review;
  const hasIssues = gaps.length > 0 || scope_creep_issues.length > 0 || quality_issues.length > 0;
  if (coverage_ok && !hasIssues) return null;

  return (
    <div className="border-b border-amber-100">
      {/* Header cliquable */}
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-4 py-2 bg-amber-50 hover:bg-amber-100 transition-colors text-left"
      >
        <AlertTriangle size={11} className="shrink-0 text-amber-600" />
        <span className="text-xs font-medium text-amber-700 flex-1">
          Couverture incomplète — {gaps.length} gap{gaps.length > 1 ? "s" : ""}
          {scope_creep_issues.length > 0 && ` · ${scope_creep_issues.length} scope creep`}
          {quality_issues.length > 0 && ` · ${quality_issues.length} qualité`}
        </span>
        <span className="text-xs text-amber-500 shrink-0">{open ? "Masquer" : "Détails"}</span>
      </button>

      {/* Détails dépliables */}
      {open && (
        <div className="px-4 py-3 bg-amber-50 space-y-2">
          {gaps.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-amber-700 mb-1">Fonctionnalités manquantes :</p>
              <ul className="space-y-1">
                {gaps.map((gap, i) => (
                  <li key={`g-${i}`} className="flex items-start gap-1.5 text-xs text-amber-800">
                    <span className="text-amber-500 shrink-0 mt-0.5">•</span>
                    <span>{gap}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {scope_creep_issues.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-orange-700 mb-1">Scope creep détecté :</p>
              <ul className="space-y-1">
                {scope_creep_issues.map((issue, i) => (
                  <li key={`sc-${i}`} className="flex items-start gap-1.5 text-xs text-orange-700">
                    <AlertTriangle size={10} className="shrink-0 mt-0.5" />
                    <span>{issue}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {quality_issues.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-blue-700 mb-1">Problèmes qualité :</p>
              <ul className="space-y-1">
                {quality_issues.map((issue, i) => (
                  <li key={`qi-${i}`} className="flex items-start gap-1.5 text-xs text-blue-700">
                    <AlertCircle size={10} className="shrink-0 mt-0.5" />
                    <span>{issue}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {suggestions.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-600 mb-1">Suggestions :</p>
              <ul className="space-y-1">
                {suggestions.map((s, i) => (
                  <li key={`sg-${i}`} className="flex items-start gap-1.5 text-xs text-slate-600">
                    <span className="text-slate-400 shrink-0 mt-0.5">›</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Composant principal StoriesSection ────────────────────────
function StoriesSection({ aiOutput, onContinue, projectId }) {
  const [storiesState, setStoriesState] = useState(aiOutput.stories ?? []);
  const [closedEpics,  setClosedEpics]  = useState(new Set());
  const [continuing,   setContinuing]   = useState(false);
  // { epicIdx: int, epicTitle: string } | null
  const [addingTo,     setAddingTo]     = useState(null);
  const epics = aiOutput.epics ?? [];

  useEffect(() => {
    setStoriesState(aiOutput.stories ?? []);
  }, [aiOutput]);

  const handleDeleted = (dbId) =>
    setStoriesState(prev => prev.filter(s => s.db_id !== dbId));

  const handleStoryAdded = (newStory) => {
    setStoriesState(prev => [...prev, newStory]);
    setAddingTo(null);
  };

  const toggleEpic = (idx) =>
    setClosedEpics(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });

  if (!storiesState.length)
    return <p className="text-slate-400 text-sm italic">Aucune story générée.</p>;

  // Regrouper par epic_id
  const grouped = storiesState.reduce((acc, s) => {
    const key = s.epic_id ?? 0;
    if (!acc[key]) acc[key] = [];
    acc[key].push(s);
    return acc;
  }, {});

  const totalPts = storiesState.reduce((sum, s) => sum + (s.story_points ?? 0), 0);
  const totalAC  = storiesState.reduce((sum, s) => sum + parseAC(s.acceptance_criteria).length, 0);

  // Épics sans stories = génération interrompue
  const missingEpics = epics.filter((_, i) => !grouped[i]);

  const handleContinue = async () => {
    if (!onContinue) return;
    setContinuing(true);
    try { await onContinue(); } finally { setContinuing(false); }
  };

  return (
    <div className="space-y-4">
      {/* Modal ajout story */}
      {addingTo && (
        <AddStoryModal
          projectId={projectId}
          epicIdx={addingTo.epicIdx}
          epicTitle={addingTo.epicTitle}
          onClose={() => setAddingTo(null)}
          onAdded={handleStoryAdded}
        />
      )}

      {/* Bannière génération incomplète */}
      {missingEpics.length > 0 && onContinue && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-700">
          <AlertCircle size={15} className="shrink-0" />
          <span className="flex-1">
            <strong>{missingEpics.length} epic{missingEpics.length > 1 ? "s" : ""}</strong> sans stories — génération interrompue.
          </span>
          <button
            onClick={handleContinue}
            disabled={continuing}
            className="flex items-center gap-1.5 text-xs font-medium bg-amber-600 text-white px-3 py-1.5 rounded-lg hover:bg-amber-700 disabled:opacity-60 shrink-0"
          >
            <PlayCircle size={13} />
            {continuing ? "Relance..." : "Continuer la génération"}
          </button>
        </div>
      )}

      {/* Statistiques globales */}
      <div className="grid grid-cols-3 gap-3">
        {[
          ["Stories",        storiesState.length],
          ["Story points",   totalPts],
          ["Critères total", totalAC],
        ].map(([k, v]) => (
          <div key={k} className="bg-slate-50 rounded-xl p-3 text-center">
            <div className="font-display font-bold text-navy text-lg">{v}</div>
            <div className="text-xs text-slate-400 mt-0.5">{k}</div>
          </div>
        ))}
      </div>

      {/* Stories groupées par epic */}
      {Object.entries(grouped).map(([epicIdx, epicStories]) => {
        const epicInfo  = epics[parseInt(epicIdx)];
        const epicPts   = epicStories.reduce((s, st) => s + (st.story_points ?? 0), 0);
        const review    = epicStories[0]?._review ?? null;
        const isOpen    = !closedEpics.has(epicIdx);
        const Chevron   = isOpen ? ChevronDown : ChevronRight;

        return (
          <div key={epicIdx} className="rounded-xl border border-slate-200 overflow-hidden">
            {/* Header epic — cliquable pour replier */}
            <button
              type="button"
              onClick={() => toggleEpic(epicIdx)}
              className="w-full flex items-center gap-2 px-4 py-2.5 bg-navy/5 border-b border-slate-200 hover:bg-navy/10 transition-colors text-left"
            >
              <Chevron size={13} className="text-slate-400 shrink-0" />
              <div className="w-5 h-5 bg-navy text-white rounded flex items-center justify-center text-xs font-bold shrink-0">
                {parseInt(epicIdx) + 1}
              </div>
              <span className="text-xs font-semibold text-navy truncate flex-1">
                {epicInfo?.title ?? `Epic ${parseInt(epicIdx) + 1}`}
              </span>
              {review?.coverage_ok === true && (
                <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full shrink-0 flex items-center gap-1">
                  <CheckCircle size={10} /> Couverture OK
                </span>
              )}
              <span className="text-xs text-slate-400 shrink-0 ml-1">
                {epicStories.length} stories · {epicPts} pts
              </span>
            </button>

            {/* Bouton + ajouter une story */}
            <button
              type="button"
              onClick={() => setAddingTo({ epicIdx: parseInt(epicIdx), epicTitle: epicInfo?.title ?? `Epic ${parseInt(epicIdx) + 1}` })}
              className="flex items-center gap-1 px-3 py-1.5 text-xs text-navy hover:bg-navy/5 border-b border-slate-200 w-full transition-colors"
            >
              <Plus size={11} /> Ajouter une story
            </button>

            {/* Contenu dépliable */}
            {isOpen && (
              <>
                <EpicReviewBanner review={review} />
                <div className="divide-y divide-slate-100 bg-white">
                  {epicStories.map((s, si) => (
                    <StoryCard key={s.db_id ?? si} story={s} onDeleted={handleDeleted} />
                  ))}
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}


// ── Carte story (vue lecture seule pour la phase refinement) ──
function RefinedStoryCard({ story }) {
  const [open, setOpen] = useState(false);
  const ac = parseAC(story.acceptance_criteria);
  const sp = story.story_points ?? "?";
  const spColor = sp <= 2 ? "bg-green-100 text-green-700"
                : sp <= 5 ? "bg-amber-100 text-amber-700"
                :           "bg-red-100 text-red-700";

  return (
    <div className="px-4 py-3">
      <div className="flex items-start gap-2">
        <span className={clsx("text-xs font-bold px-1.5 py-0.5 rounded shrink-0 mt-0.5", spColor)}>
          {sp}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-navy leading-snug">{story.title}</p>
          {story.description && (
            <p className="text-xs text-slate-500 mt-0.5 leading-relaxed line-clamp-2">{story.description}</p>
          )}
          {ac.length > 0 && (
            <button
              onClick={() => setOpen(v => !v)}
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 mt-1.5"
            >
              {open ? <ChevronDown size={11}/> : <ChevronRight size={11}/>}
              {ac.length} critère{ac.length > 1 ? "s" : ""}
            </button>
          )}
          {open && (
            <ul className="mt-1.5 space-y-1 pl-2">
              {ac.map((c, i) => (
                <li key={i} className="text-xs text-slate-600 leading-snug flex gap-1.5">
                  <span className="text-cyan shrink-0 mt-0.5">›</span>{c}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Validation round-by-round ─────────────────────────────────
function RoundReviewSection({ aiOutput, onApplyRound }) {
  const refinedStories  = aiOutput.refined_stories   ?? [];
  const storiesBefore   = aiOutput.stories_before_round ?? [];
  const currentRound    = aiOutput.current_round     ?? 1;
  const roundData       = (aiOutput.refinement_rounds ?? []).find(r => r.round === currentRound);
  const patches         = (roundData?.stories_patch ?? []).filter(p => p.applied !== false && p.field !== "flag");
  const consensus       = aiOutput.consensus ?? false;

  // choices : { db_id_str: "new" | "old" }
  const [choices, setChoices] = useState(() => {
    const init = {};
    patches.forEach(p => { if (p.db_id) init[String(p.db_id)] = "new"; });
    return init;
  });
  const [submitting, setSubmitting] = useState(false);

  // Index des stories avant/après par db_id
  const beforeById = Object.fromEntries(storiesBefore.map(s => [String(s.db_id ?? ""), s]));
  const afterById  = Object.fromEntries(refinedStories.map(s => [String(s.db_id ?? ""), s]));

  // Stories qui ont au moins un patch applicable
  const patchedDbIds = [...new Set(patches.map(p => String(p.db_id)).filter(Boolean))];

  const setChoice = (dbId, val) =>
    setChoices(prev => ({ ...prev, [dbId]: val }));

  const handleSubmit = async (continueRefinement) => {
    setSubmitting(true);
    // Les stories sans patch gardent automatiquement "new"
    const allChoices = {};
    refinedStories.forEach(s => {
      const key = String(s.db_id ?? "");
      allChoices[key] = choices[key] ?? "new";
    });
    await onApplyRound?.(allChoices, continueRefinement);
    setSubmitting(false);
  };

  const changesCount   = patchedDbIds.length;
  const newCount       = patchedDbIds.filter(id => (choices[id] ?? "new") === "new").length;
  const oldCount       = changesCount - newCount;

  return (
    <div className="space-y-4">

      {/* En-tête du round */}
      <div className="flex items-center gap-3 bg-violet-50 border border-violet-200 rounded-xl px-4 py-3">
        <div className="w-8 h-8 rounded-full bg-violet-600 text-white flex items-center justify-center font-bold text-sm shrink-0">
          {currentRound}
        </div>
        <div className="flex-1">
          <p className="text-sm font-semibold text-violet-800">Round {currentRound} terminé</p>
          <p className="text-xs text-violet-600">
            {changesCount} story(-ies) modifiée(s) · {patches.length} patch(es) appliqué(s)
            {consensus && " · Consensus atteint"}
          </p>
        </div>
        {consensus && (
          <span className="flex items-center gap-1 text-xs bg-green-100 text-green-700 px-2.5 py-1 rounded-full font-semibold">
            <CheckCircle size={11} /> Consensus
          </span>
        )}
      </div>

      {/* Résumés PO / TL */}
      {roundData && (
        <div className="space-y-1.5">
          {roundData.po_comment && (
            <div className="flex items-start gap-2 text-xs text-slate-600 bg-violet-50 rounded-lg px-3 py-2">
              <Users size={12} className="text-violet-500 shrink-0 mt-0.5" />
              <span><span className="font-semibold text-violet-700">PO :</span> {roundData.po_comment}</span>
            </div>
          )}
          {roundData.tech_comment && (
            <div className="flex items-start gap-2 text-xs text-slate-600 bg-cyan-50 rounded-lg px-3 py-2">
              <Wrench size={12} className="text-cyan-600 shrink-0 mt-0.5" />
              <span><span className="font-semibold text-cyan-700">Tech Lead :</span> {roundData.tech_comment}</span>
            </div>
          )}
        </div>
      )}

      {/* Diff story par story */}
      {patchedDbIds.length === 0 ? (
        <p className="text-slate-400 text-sm italic text-center py-4">Aucune modification proposée ce round.</p>
      ) : (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
            Choisissez pour chaque story modifiée
          </p>

          {patchedDbIds.map(dbId => {
            const storyAfter  = afterById[dbId]  ?? {};
            const storyBefore = beforeById[dbId] ?? {};
            const storyPatches = patches.filter(p => String(p.db_id) === dbId);
            const choice = choices[dbId] ?? "new";

            return (
              <div key={dbId} className={`rounded-xl border-2 overflow-hidden transition-colors ${
                choice === "new" ? "border-green-300" : "border-slate-300"
              }`}>
                {/* Header story */}
                <div className="px-4 py-2.5 bg-slate-50 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-xs text-slate-400 shrink-0">db_id={dbId}</span>
                    <span className="text-xs font-semibold text-navy truncate">
                      {storyAfter.title ?? storyBefore.title ?? "—"}
                    </span>
                  </div>
                  {/* Toggle new / old */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => setChoice(dbId, "new")}
                      className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
                        choice === "new"
                          ? "bg-green-500 text-white"
                          : "bg-slate-100 text-slate-500 hover:bg-green-100 hover:text-green-700"
                      }`}
                    >
                      Garder nouveau
                    </button>
                    <button
                      onClick={() => setChoice(dbId, "old")}
                      className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
                        choice === "old"
                          ? "bg-slate-500 text-white"
                          : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                      }`}
                    >
                      Garder ancien
                    </button>
                  </div>
                </div>

                {/* Détail des changements */}
                <div className="divide-y divide-slate-100 bg-white">
                  {storyPatches.map((p, pi) => (
                    <div key={pi} className="px-4 py-2.5 grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs text-slate-400 mb-1 font-mono">
                          {p.field} — <span className="text-slate-500">avant</span>
                        </p>
                        <p className={`text-xs rounded-lg px-2 py-1.5 bg-red-50 text-red-700 ${
                          choice === "old" ? "ring-2 ring-slate-400" : ""
                        }`}>
                          {Array.isArray(p.old_value)
                            ? p.old_value.join(" · ") || "—"
                            : String(p.old_value ?? "—")}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-400 mb-1 font-mono">
                          {p.field} — <span className="text-green-600">après</span>
                        </p>
                        <p className={`text-xs rounded-lg px-2 py-1.5 bg-green-50 text-green-700 ${
                          choice === "new" ? "ring-2 ring-green-400" : ""
                        }`}>
                          {Array.isArray(p.new_value_applied)
                            ? p.new_value_applied.join(" · ") || "—"
                            : String(p.new_value_applied ?? p.new_value ?? "—")}
                        </p>
                      </div>
                      {p.reason && (
                        <p className="col-span-2 text-xs text-slate-400 italic">
                          Raison : {p.reason}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Barre de synthèse + boutons */}
      <div className="bg-slate-50 rounded-xl px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3 text-xs text-slate-600">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block" />
            {newCount} nouveau{newCount > 1 ? "x" : ""}
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-400 inline-block" />
            {oldCount} ancien{oldCount > 1 ? "s" : ""}
          </span>
          <span className="text-slate-400">
            {refinedStories.length - changesCount} stories inchangées
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSubmit(false)}
            disabled={submitting}
            className="flex items-center gap-1.5 text-xs font-semibold border border-slate-300 text-slate-600 hover:bg-slate-100 px-3 py-2 rounded-lg transition-colors disabled:opacity-50"
          >
            Arrêter le raffinement
          </button>
          {!consensus && currentRound < 3 && (
            <button
              onClick={() => handleSubmit(true)}
              disabled={submitting}
              className="flex items-center gap-1.5 text-xs font-semibold bg-violet-600 hover:bg-violet-700 text-white px-3 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              <PlayCircle size={13} />
              {submitting ? "En cours..." : `Continuer — Round ${currentRound + 1}`}
            </button>
          )}
          {(consensus || currentRound >= 3) && (
            <button
              onClick={() => handleSubmit(false)}
              disabled={submitting}
              className="flex items-center gap-1.5 text-xs font-semibold bg-green-600 hover:bg-green-700 text-white px-3 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              <CheckCircle size={13} />
              Finaliser le raffinement
            </button>
          )}
        </div>
      </div>
    </div>
  );
}


// ── [DEV] Panneau debug raffinement ───────────────────────────
function RefinementDebugPanel({ refinedStories, refinementRounds, epics }) {
  const [open, setOpen] = useState(false);

  // Construire la table local→global→db_id par epic
  const idMappings = epics.map((epic, epicIdx) => {
    const epicStories = refinedStories
      .map((s, globalPos) => ({ ...s, _globalPos: globalPos }))
      .filter(s => s.epic_id === epicIdx);
    return { epicIdx, epicTitle: epic.title, stories: epicStories };
  }).filter(e => e.stories.length > 0);

  return (
    <div className="rounded-xl border-2 border-dashed border-orange-300 bg-orange-50 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-orange-100 transition-colors"
      >
        {open ? <ChevronDown size={13} className="text-orange-500" /> : <ChevronRight size={13} className="text-orange-500" />}
        <span className="text-xs font-bold text-orange-600 font-mono">🛠 DEV — Debug raffinement</span>
        <span className="ml-auto text-xs text-orange-400 font-mono">
          {refinedStories.length} stories · {refinementRounds.length} round(s)
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 font-mono text-xs">

          {/* ── Table de correspondance local→db_id par epic ── */}
          <div>
            <p className="font-bold text-orange-700 mb-2">Table local_idx → db_id (par epic)</p>
            {idMappings.map(({ epicIdx, epicTitle, stories }) => (
              <div key={epicIdx} className="mb-3">
                <p className="text-orange-600 font-semibold mb-1">
                  Epic {epicIdx} — {epicTitle?.slice(0, 45)}
                </p>
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-orange-100">
                      <th className="px-2 py-1 border border-orange-200">local_idx</th>
                      <th className="px-2 py-1 border border-orange-200">global_pos</th>
                      <th className="px-2 py-1 border border-orange-200">db_id</th>
                      <th className="px-2 py-1 border border-orange-200">SP</th>
                      <th className="px-2 py-1 border border-orange-200">title (35 chars)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stories.map((s, localIdx) => (
                      <tr key={localIdx} className={localIdx % 2 === 0 ? "bg-white" : "bg-orange-50"}>
                        <td className="px-2 py-1 border border-orange-200 text-center font-bold">{localIdx}</td>
                        <td className="px-2 py-1 border border-orange-200 text-center">{s._globalPos}</td>
                        <td className="px-2 py-1 border border-orange-200 text-center font-bold text-green-700">
                          {s.db_id ?? <span className="text-red-500">⚠ manquant</span>}
                        </td>
                        <td className="px-2 py-1 border border-orange-200 text-center">{s.story_points ?? '?'}</td>
                        <td className="px-2 py-1 border border-orange-200 text-slate-600">{(s.title ?? '').slice(0, 500)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          {/* ── Détail des patches par round ── */}
          <div>
            <p className="font-bold text-orange-700 mb-2">Patches appliqués par round</p>
            {refinementRounds.map(round => {
              const patches = round.stories_patch ?? [];
              const actionable = patches.filter(p => p.field !== 'flag');
              const major = actionable.filter(p => ['title', 'story_points'].includes(p.field)).length;
              return (
                <div key={round.round} className="mb-3 border border-orange-200 rounded-lg overflow-hidden">
                  <div className="flex items-center gap-3 px-3 py-1.5 bg-orange-100">
                    <span className="font-bold text-orange-800">Round {round.round}</span>
                    <span className="text-orange-600">total={patches.length} · actionable={actionable.length} · majeurs={major}</span>
                    {round.consensus && <span className="ml-auto text-green-700 font-bold">✓ CONSENSUS</span>}
                  </div>
                  {patches.length === 0 ? (
                    <p className="px-3 py-2 text-slate-400 italic">Aucun patch ce round.</p>
                  ) : (
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="bg-orange-50">
                          <th className="px-2 py-1 border border-orange-200">local_idx</th>
                          <th className="px-2 py-1 border border-orange-200">field</th>
                          <th className="px-2 py-1 border border-orange-200">new_value</th>
                          <th className="px-2 py-1 border border-orange-200">reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {patches.map((p, pi) => (
                          <tr key={pi} className={p.field === 'flag' ? 'opacity-40' : (pi % 2 === 0 ? 'bg-white' : 'bg-orange-50')}>
                            <td className="px-2 py-1 border border-orange-200 text-center font-bold">{p.story_local_idx ?? '?'}</td>
                            <td className={`px-2 py-1 border border-orange-200 font-semibold ${
                              p.field === 'story_points' ? 'text-blue-700' :
                              p.field === 'title'        ? 'text-purple-700' :
                              p.field === 'flag'         ? 'text-slate-400' :
                              'text-orange-700'
                            }`}>{p.field}</td>
                            <td className="px-2 py-1 border border-orange-200 text-slate-700 max-w-xs truncate">
                              {p.new_value !== undefined ? String(p.new_value).slice(0, 50) :
                               p.value      !== undefined ? String(p.value).slice(0, 50) : '—'}
                            </td>
                            <td className="px-2 py-1 border border-orange-200 text-slate-500 max-w-xs truncate">
                              {(p.reason ?? '').slice(0, 60)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              );
            })}
          </div>

          {/* ── Stories sans db_id ── */}
          {refinedStories.filter(s => !s.db_id).length > 0 && (
            <div className="bg-red-50 border border-red-300 rounded-lg px-3 py-2">
              <p className="font-bold text-red-700 mb-1">⚠ Stories sans db_id ({refinedStories.filter(s => !s.db_id).length}) — ne seront PAS sauvegardées en base !</p>
              {refinedStories.filter(s => !s.db_id).map((s, i) => (
                <p key={i} className="text-red-600">epic={s.epic_id} | {(s.title ?? '').slice(0, 50)}</p>
              ))}
            </div>
          )}

        </div>
      )}
    </div>
  );
}

// ── Composant principal RefinementSection ─────────────────────
function RefinementSection({ aiOutput, onContinue }) {
  const refinedStories   = aiOutput.refined_stories   ?? [];
  const refinementRounds = aiOutput.refinement_rounds ?? [];
  const epics            = aiOutput.epics             ?? [];
  const [closedEpics,   setClosedEpics]   = useState(new Set());
  const [roundsOpen,    setRoundsOpen]    = useState(false);

  if (!refinedStories.length)
    return <p className="text-slate-400 text-sm italic">Aucune story raffinée disponible.</p>;

  const toggleEpic = (idx) =>
    setClosedEpics(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });

  const grouped = refinedStories.reduce((acc, s) => {
    const key = s.epic_id ?? 0;
    if (!acc[key]) acc[key] = [];
    acc[key].push(s);
    return acc;
  }, {});

  const totalPts     = refinedStories.reduce((s, st) => s + (st.story_points ?? 0), 0);
  const totalPatches = refinementRounds.reduce((s, r) => s + (r.patches_count ?? 0), 0);
  const consensusRound = refinementRounds.find(r => r.consensus)?.round ?? null;

  return (
    <div className="space-y-4">
      {/* Bouton Relancer le raffinement */}
      {onContinue && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
          <AlertTriangle size={15} className="text-amber-500 shrink-0" />
          <span className="text-xs text-amber-700 flex-1">
            Relancez le raffinement PO ↔ Tech Lead pour affiner à nouveau les stories.
          </span>
          <button
            onClick={onContinue}
            className="flex items-center gap-1.5 text-xs font-semibold bg-amber-500 hover:bg-amber-600 text-white px-3 py-1.5 rounded-lg transition-colors shrink-0"
          >
            <PlayCircle size={13} /> Relancer le raffinement
          </button>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        {[
          ["Stories raffinées", refinedStories.length],
          ["Story points",      totalPts],
          ["Patches appliqués", totalPatches],
        ].map(([k, v]) => (
          <div key={k} className="bg-slate-50 rounded-xl p-3 text-center">
            <div className="font-display font-bold text-navy text-lg">{v}</div>
            <div className="text-xs text-slate-400 mt-0.5">{k}</div>
          </div>
        ))}
      </div>

      {/* Consensus banner */}
      {consensusRound && (
        <div className="flex items-center gap-2 bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-2.5 text-sm">
          <CheckCircle size={14} className="shrink-0" />
          Consensus PO ↔ Tech Lead atteint au <strong className="ml-1">round {consensusRound}</strong>
        </div>
      )}

      {/* Historique des rounds (collapsible) */}
      {refinementRounds.length > 0 && (
        <div className="rounded-xl border border-slate-200 overflow-hidden">
          <button
            onClick={() => setRoundsOpen(v => !v)}
            className="w-full flex items-center gap-2 px-4 py-2.5 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
          >
            {roundsOpen ? <ChevronDown size={13} className="text-slate-400"/> : <ChevronRight size={13} className="text-slate-400"/>}
            <Layers size={13} className="text-slate-500 shrink-0" />
            <span className="text-xs font-semibold text-slate-700">
              Historique des rounds ({refinementRounds.length})
            </span>
          </button>

          {roundsOpen && (
            <div className="divide-y divide-slate-100">
              {refinementRounds.map((round) => (
                <div key={round.round} className="px-4 py-3 space-y-2 bg-white">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold bg-navy text-white px-2 py-0.5 rounded-full">
                      Round {round.round}
                    </span>
                    <span className="text-xs text-slate-400">{round.patches_count ?? 0} patch(es)</span>
                    {round.consensus && (
                      <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full flex items-center gap-1 ml-auto">
                        <CheckCircle size={10}/> Consensus
                      </span>
                    )}
                  </div>
                  {round.po_comment && (
                    <div className="flex items-start gap-2 text-xs text-slate-600">
                      <Users size={12} className="text-violet-500 shrink-0 mt-0.5"/>
                      <span><span className="font-medium text-violet-700">PO :</span> {round.po_comment}</span>
                    </div>
                  )}
                  {round.tech_comment && (
                    <div className="flex items-start gap-2 text-xs text-slate-600">
                      <Wrench size={12} className="text-cyan shrink-0 mt-0.5"/>
                      <span><span className="font-medium text-cyan-700">TL :</span> {round.tech_comment}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* [DEV] Panneau debug */}
      <RefinementDebugPanel
        refinedStories={refinedStories}
        refinementRounds={refinementRounds}
        epics={epics}
      />

      {/* Stories groupées par epic (collapsibles) */}
      {Object.entries(grouped).map(([epicIdx, epicStories]) => {
        const epicInfo = epics[parseInt(epicIdx)];
        const epicPts  = epicStories.reduce((s, st) => s + (st.story_points ?? 0), 0);
        const isOpen   = !closedEpics.has(epicIdx);
        const Chevron  = isOpen ? ChevronDown : ChevronRight;

        return (
          <div key={epicIdx} className="rounded-xl border border-slate-200 overflow-hidden">
            <button
              type="button"
              onClick={() => toggleEpic(epicIdx)}
              className="w-full flex items-center gap-2 px-4 py-2.5 bg-navy/5 border-b border-slate-200 hover:bg-navy/10 transition-colors text-left"
            >
              <Chevron size={13} className="text-slate-400 shrink-0" />
              <div className="w-5 h-5 bg-navy text-white rounded flex items-center justify-center text-xs font-bold shrink-0">
                {parseInt(epicIdx) + 1}
              </div>
              <span className="text-xs font-semibold text-navy truncate flex-1">
                {epicInfo?.title ?? `Epic ${parseInt(epicIdx) + 1}`}
              </span>
              <span className="text-xs text-slate-400 shrink-0">
                {epicStories.length} stories · {epicPts} pts
              </span>
            </button>
            {isOpen && (
              <div className="divide-y divide-slate-100 bg-white">
                {epicStories.map((s, si) => (
                  <RefinedStoryCard key={s.db_id ?? si} story={s} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}


// ── Modal de confirmation suppression ─────────────────────────
function ConfirmDeleteModal({ epicTitle, onConfirm, onCancel, loading }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-100">
          <div className="w-9 h-9 rounded-full bg-red-100 flex items-center justify-center shrink-0">
            <Trash2 size={16} className="text-red-500" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-800">Supprimer l'epic</p>
            <p className="text-xs text-slate-400">Cette action est irréversible</p>
          </div>
          <button onClick={onCancel} className="ml-auto text-slate-300 hover:text-slate-500">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          <p className="text-sm text-slate-600">
            Vous allez supprimer l'epic{" "}
            <span className="font-semibold text-slate-800">"{epicTitle}"</span>{" "}
            ainsi que toutes ses user stories associées.
          </p>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 bg-slate-50 border-t border-slate-100">
          <button
            onClick={onCancel}
            disabled={loading}
            className="text-xs text-slate-500 hover:text-slate-700 px-3 py-1.5 rounded-lg hover:bg-slate-100 transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex items-center gap-1.5 text-xs font-semibold bg-red-500 hover:bg-red-600 text-white px-4 py-1.5 rounded-lg transition-colors disabled:opacity-50"
          >
            <Trash2 size={12} />
            {loading ? "Suppression…" : "Supprimer"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Stratégies disponibles ─────────────────────────────────────
const STRATEGIES = [
  { value: "by_feature",       label: "By feature" },
  { value: "by_user_role",     label: "By user role" },
  { value: "by_workflow_step", label: "By workflow step" },
  { value: "by_component",     label: "By component" },
];

// ── Section epics éditable ─────────────────────────────────────
function EpicsSection({ aiOutput, projectId, onRefresh }) {
  const [epics, setEpics]         = useState([]);
  const [loadingEpics, setLoadingEpics] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm]   = useState({});
  const [saving, setSaving]       = useState(false);
  const [deleting, setDeleting]   = useState(null);
  const [confirmDeleteIdx, setConfirmDeleteIdx] = useState(null);
  const [showAdd, setShowAdd]     = useState(false);
  const [addForm, setAddForm]     = useState({ title: "", description: "", splitting_strategy: "by_feature" });
  const [adding, setAdding]       = useState(false);
  const [error, setError]         = useState(null);

  // Charge les epics avec db_id depuis l'API
  const loadEpics = async () => {
    if (!projectId) return;
    try {
      const data = await getProjectEpics(projectId);
      setEpics(data);
    } catch {
      // fallback sur aiOutput si l'API échoue
      setEpics(aiOutput?.epics ?? []);
    } finally {
      setLoadingEpics(false);
    }
  };

  useEffect(() => { loadEpics(); }, [projectId]);

  // ── Helpers ────────────────────────────────────────────────
  // Les dicts epics n'ont pas de db_id — on le récupère via l'index
  // en relisant la liste depuis la DB après chaque opération (onRefresh)
  // Pour matcher index → db_id on a besoin de l'ordre DB = ordre state
  // On stocke db_id dans epics si présent (enrichissement possible plus tard)

  const startEdit = (i) => {
    setEditingId(i);
    setEditForm({
      title:              epics[i].title ?? "",
      description:        epics[i].description ?? "",
      splitting_strategy: epics[i].splitting_strategy ?? "by_feature",
    });
    setError(null);
  };

  const cancelEdit = () => { setEditingId(null); setError(null); };

  const saveEdit = async (i) => {
    const epic = epics[i];
    if (!epic.db_id) { setError("ID epic manquant — rechargez la page."); return; }
    setSaving(true);
    try {
      await updateEpic(epic.db_id, editForm);
      const updated = epics.map((e, idx) => idx === i ? { ...e, ...editForm } : e);
      setEpics(updated);
      setEditingId(null);
      onRefresh?.();
    } catch { setError("Erreur lors de la modification."); }
    finally { setSaving(false); }
  };

  const handleDelete = async (i) => {
    const epic = epics[i];
    if (!epic.db_id) { setError("ID epic manquant — rechargez la page."); return; }
    setConfirmDeleteIdx(i);
  };

  const confirmDelete = async () => {
    const i    = confirmDeleteIdx;
    const epic = epics[i];
    setDeleting(i);
    try {
      await deleteEpic(epic.db_id);
      setEpics(epics.filter((_, idx) => idx !== i));
      setConfirmDeleteIdx(null);
      onRefresh?.();
    } catch { setError("Erreur lors de la suppression."); }
    finally { setDeleting(null); }
  };

  const handleAdd = async () => {
    if (!addForm.title.trim()) { setError("Le titre est obligatoire."); return; }
    setAdding(true);
    try {
      const created = await addEpic(projectId, addForm);
      setEpics([...epics, {
        db_id:              created.epic_id,
        title:              created.title,
        description:        created.description,
        splitting_strategy: created.splitting_strategy,
      }]);
      setAddForm({ title: "", description: "", splitting_strategy: "by_feature" });
      setShowAdd(false);
      onRefresh?.();
    } catch { setError("Erreur lors de l'ajout."); }
    finally { setAdding(false); }
  };

  return (
    <div className="space-y-2">
      {/* Modal suppression */}
      {confirmDeleteIdx !== null && (
        <ConfirmDeleteModal
          epicTitle={epics[confirmDeleteIdx]?.title ?? ""}
          loading={deleting === confirmDeleteIdx}
          onConfirm={confirmDelete}
          onCancel={() => setConfirmDeleteIdx(null)}
        />
      )}

      {error && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center gap-2">
          <AlertCircle size={13} /> {error}
          <button onClick={() => setError(null)} className="ml-auto"><X size={12} /></button>
        </div>
      )}

      {epics.map((epic, i) => (
        <div key={epic.db_id ?? i} className="rounded-xl border border-slate-200 overflow-hidden">
          {editingId === i ? (
            /* ── Mode édition ──────────────────────────────── */
            <div className="p-3 bg-slate-50 space-y-2">
              <input
                className="w-full text-sm font-medium border border-slate-300 rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan"
                value={editForm.title}
                onChange={e => setEditForm(f => ({ ...f, title: e.target.value }))}
                placeholder="Titre de l'epic"
              />
              <textarea
                className="w-full text-xs border border-slate-300 rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan resize-none"
                rows={3}
                value={editForm.description}
                onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Description"
              />
              <select
                className="text-xs border border-slate-300 rounded-lg px-2 py-1.5 focus:outline-none focus:border-cyan bg-white"
                value={editForm.splitting_strategy}
                onChange={e => setEditForm(f => ({ ...f, splitting_strategy: e.target.value }))}
              >
                {STRATEGIES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
              <div className="flex gap-2 pt-1">
                <button
                  onClick={() => saveEdit(i)}
                  disabled={saving}
                  className="flex items-center gap-1 text-xs bg-navy text-white rounded-lg px-3 py-1.5 hover:bg-navy/90 disabled:opacity-50"
                >
                  <Save size={12} /> {saving ? "Sauvegarde…" : "Enregistrer"}
                </button>
                <button
                  onClick={cancelEdit}
                  className="text-xs text-slate-500 hover:text-slate-700 px-2"
                >
                  Annuler
                </button>
              </div>
            </div>
          ) : (
            /* ── Mode lecture ──────────────────────────────── */
            <div className="flex items-start gap-3 p-3 bg-slate-50 group">
              <div className="w-6 h-6 bg-navy text-white rounded-lg flex items-center justify-center text-xs font-bold shrink-0">
                {i + 1}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-navy">{epic.title}</div>
                {epic.description && (
                  <div className="text-xs text-slate-500 mt-0.5">{epic.description}</div>
                )}
                {epic.splitting_strategy && (
                  <div className="text-xs text-slate-400 mt-1">
                    Stratégie : <span className="text-cyan font-medium">{epic.splitting_strategy.replace(/_/g, " ")}</span>
                  </div>
                )}
              </div>
              {/* Actions — visibles au hover */}
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                <button
                  onClick={() => startEdit(i)}
                  title="Modifier"
                  className="p-1 text-slate-400 hover:text-navy hover:bg-slate-100 rounded-lg"
                >
                  <Pencil size={14} />
                </button>
                <button
                  onClick={() => handleDelete(i)}
                  disabled={deleting === i}
                  title="Supprimer"
                  className="p-1 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg disabled:opacity-50"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      ))}

      {/* ── Formulaire ajout ─────────────────────────────── */}
      {showAdd ? (
        <div className="rounded-xl border border-dashed border-cyan bg-cyan/5 p-3 space-y-2">
          <p className="text-xs font-medium text-cyan">Nouvel epic</p>
          <input
            className="w-full text-sm border border-slate-300 rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan"
            placeholder="Titre *"
            value={addForm.title}
            onChange={e => setAddForm(f => ({ ...f, title: e.target.value }))}
          />
          <textarea
            className="w-full text-xs border border-slate-300 rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan resize-none"
            rows={2}
            placeholder="Description (optionnel)"
            value={addForm.description}
            onChange={e => setAddForm(f => ({ ...f, description: e.target.value }))}
          />
          <select
            className="text-xs border border-slate-300 rounded-lg px-2 py-1.5 focus:outline-none focus:border-cyan bg-white"
            value={addForm.splitting_strategy}
            onChange={e => setAddForm(f => ({ ...f, splitting_strategy: e.target.value }))}
          >
            {STRATEGIES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleAdd}
              disabled={adding}
              className="flex items-center gap-1 text-xs bg-cyan text-white rounded-lg px-3 py-1.5 hover:bg-cyan/90 disabled:opacity-50"
            >
              <Save size={12} /> {adding ? "Ajout…" : "Ajouter"}
            </button>
            <button
              onClick={() => { setShowAdd(false); setError(null); }}
              className="text-xs text-slate-500 hover:text-slate-700 px-2"
            >
              Annuler
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => { setShowAdd(true); setError(null); }}
          className="w-full flex items-center justify-center gap-2 text-xs text-slate-400 hover:text-cyan border border-dashed border-slate-200 hover:border-cyan rounded-xl py-2.5 transition-colors"
        >
          <span className="text-lg leading-none">+</span> Ajouter un epic
        </button>
      )}
    </div>
  );
}


export default function PhaseResult({ phaseId, aiOutput, onContinue, onApplyRound, projectId, onRefresh }) {
  if (!aiOutput && phaseId !== "extract")
    return <p className="text-slate-400 text-sm italic">Aucun résultat disponible pour cette phase.</p>;
  if (!aiOutput) aiOutput = {};

  if (phaseId === "extract") {
    const { filename, file_size, pages_est, chars, image_count, oversized_pages,
            preview, security_scan,
            architecture_detected, architecture_description, architecture_details } = aiOutput;

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

        <div className="grid grid-cols-4 gap-3">
          {[
            ["Pages",          pages_est ?? "—"],
            ["Images",         image_count != null ? image_count : "—"],
            ["Caractères",     chars ? chars.toLocaleString("fr-FR") : "—"],
            ["Taille fichier", file_size ? `${(file_size / 1024).toFixed(0)} KB` : "—"],
          ].map(([k, v]) => (
            <div key={k} className="bg-slate-50 rounded-xl p-3 text-center">
              <div className="font-display font-bold text-navy text-lg">{v}</div>
              <div className="text-xs text-slate-400 mt-0.5">{k}</div>
            </div>
          ))}
        </div>

        {/* Avertissement images trop grandes pour le VLM */}
        {oversized_pages?.length > 0 && (
          <div className="flex items-start gap-2 bg-orange-50 border border-orange-200 text-orange-700 rounded-xl px-4 py-3 text-xs">
            <AlertTriangle size={14} className="shrink-0 mt-0.5" />
            <span>
              <span className="font-semibold">Image(s) trop grande(s) pour le VLM</span>
              {" — "}page{oversized_pages.length > 1 ? "s" : ""} {oversized_pages.join(", ")} ignorée{oversized_pages.length > 1 ? "s" : ""} (limite 4 MB).
              L'analyse d'architecture sur ces pages n'a pas été effectuée.
            </span>
          </div>
        )}

        {filename && (
          <div className="flex items-center gap-2 text-sm text-slate-600 bg-slate-50 rounded-xl px-3 py-2">
            <FileText size={14} className="text-cyan shrink-0" />
            <span className="font-medium truncate">{filename}</span>
          </div>
        )}

        {/* Résultat VLM — détection d'architecture */}
        {architecture_detected === true ? (
          <div className="rounded-xl border border-cyan-200 bg-cyan-50 overflow-hidden">
            {/* Header */}
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-cyan-200">
              <Component size={14} className="text-cyan shrink-0" />
              <span className="text-sm font-semibold text-cyan-800">
                Architecture détectée — {architecture_details?.architecture_type ?? "type inconnu"}
              </span>
              <span className="ml-auto text-xs bg-cyan-100 text-cyan-700 px-2 py-0.5 rounded-full font-medium">VLM</span>
            </div>

            <div className="px-4 py-3 space-y-3">
              {/* Description globale */}
              {architecture_description && (
                <p className="text-xs text-cyan-900 leading-relaxed">{architecture_description}</p>
              )}

              {/* Layers */}
              {architecture_details?.layers?.length > 0 && (() => {
                // Noms des agents et sources déjà présents dans les couches → pour éviter la redondance
                const allLayerComponents = new Set(
                  architecture_details.layers.flatMap(l => l.components ?? []).map(c => c.toLowerCase())
                );
                const agentNames     = (architecture_details.agents ?? []).map(a => a.name.toLowerCase());
                const dataSources    = (architecture_details.data_sources ?? []).map(d => d.toLowerCase());
                const agentsInLayers = agentNames.length > 0 && agentNames.every(n => allLayerComponents.has(n));
                const sourcesInLayers= dataSources.length > 0 && dataSources.every(s => allLayerComponents.has(s));

                return (
                  <>
                    <div>
                      <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1.5">Couches</p>
                      <div className="space-y-1.5">
                        {architecture_details.layers.map((l, i) => {
                          // Ne pas afficher le role s'il est identique au name
                          const showRole = l.role && l.role.toLowerCase() !== (l.name ?? "").toLowerCase();
                          return (
                            <div key={i} className="bg-white border border-cyan-100 rounded-lg px-3 py-2">
                              <p className="text-xs font-semibold text-navy">
                                {l.name || <span className="text-slate-400 italic">Zone {i + 1}</span>}
                              </p>
                              {showRole && <p className="text-xs text-slate-500 mt-0.5">{l.role}</p>}
                              {l.components?.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {l.components.map((c, j) => (
                                    <span key={j} className="text-xs bg-cyan-50 text-cyan-700 px-1.5 py-0.5 rounded">{c}</span>
                                  ))}
                                </div>
                              )}
                              {l.technologies?.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {l.technologies.map((t, j) => (
                                    <span key={j} className="text-xs bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded">{t}</span>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Grille : APIs, Data sources (masquées si déjà dans les couches), Protocoles… */}
                    {[
                      ["APIs",              architecture_details?.apis,                   "bg-violet-50 text-violet-700"],
                      ...(!sourcesInLayers ? [["Sources de données", architecture_details?.data_sources, "bg-amber-50 text-amber-700"]] : []),
                      ["Protocoles",        architecture_details?.communication_protocols,"bg-blue-50 text-blue-700"],
                      ["Sécurité",          architecture_details?.security_mechanisms,    "bg-red-50 text-red-700"],
                      ["MCP Servers",       architecture_details?.mcp_servers,            "bg-emerald-50 text-emerald-700"],
                      ["Services externes", architecture_details?.external_services,      "bg-slate-100 text-slate-600"],
                      ["Déploiement",       architecture_details?.deployment,             "bg-indigo-50 text-indigo-700"],
                    ].filter(([, items]) => items?.length > 0).map(([label, items, cls]) => (
                      <div key={label}>
                        <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">{label}</p>
                        <div className="flex flex-wrap gap-1">
                          {items.map((item, idx) => (
                            <span key={idx} className={`text-xs px-2 py-0.5 rounded-full ${cls}`}>{item}</span>
                          ))}
                        </div>
                      </div>
                    ))}

                    {/* Agents — masqués si tous déjà listés comme composants dans une couche */}
                    {!agentsInLayers && architecture_details?.agents?.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">Agents</p>
                        <div className="space-y-1">
                          {architecture_details.agents.map((a, i) => (
                            <div key={i} className="flex items-start gap-2 text-xs">
                              <span className="font-medium text-navy shrink-0">{a.name}</span>
                              {a.role && <span className="text-slate-500">— {a.role}</span>}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Orchestration — masquée si identique au nom d'une couche */}
                    {architecture_details?.orchestration &&
                     !architecture_details.layers.some(l => l.name?.toLowerCase() === architecture_details.orchestration?.toLowerCase()) && (
                      <div>
                        <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">Orchestration</p>
                        <p className="text-xs text-slate-700">{architecture_details.orchestration}</p>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          </div>
        ) : architecture_detected === false ? (
          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 text-slate-500 rounded-xl px-4 py-3 text-sm">
            <AlertCircle size={14} className="shrink-0" />
            <span>Aucune architecture détectée — sera générée automatiquement en phase Architecture.</span>
          </div>
        ) : null}

        {preview && (
          <div>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              <Eye size={12} /> Texte extrait (contenu complet)
            </div>
            <pre className="text-xs text-slate-700 bg-slate-50 border border-slate-200 rounded-xl p-4
                            overflow-auto whitespace-pre-wrap leading-relaxed font-mono">
              {preview}
            </pre>
          </div>
        )}
      </div>
    );
  }

  if (phaseId === "epics") {
    return <EpicsSection aiOutput={aiOutput} projectId={projectId} onRefresh={onRefresh} />;
  }

  if (phaseId === "stories") {
    return <StoriesSection aiOutput={aiOutput} onContinue={onContinue} projectId={projectId} />;
  }

  if (phaseId === "refinement") {
    if (aiOutput.awaiting_round_review) {
      return <RoundReviewSection aiOutput={aiOutput} onApplyRound={onApplyRound} />;
    }
    return <RefinementSection aiOutput={aiOutput} onContinue={onContinue} />;
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
