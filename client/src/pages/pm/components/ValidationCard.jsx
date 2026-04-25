import { useState, useMemo } from "react";
import { Zap, ThumbsUp, ThumbsDown, AlertCircle, Loader,
         ChevronDown, ChevronRight, Target } from "lucide-react";
import clsx from "clsx";

// ── Helpers ────────────────────────────────────────────────────

function parseAC(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  try { return JSON.parse(raw); } catch { return []; }
}

// ── Sélecteur d'epics (phase "epics") ─────────────────────────
function EpicsSelector({ epics, selected, onChange }) {
  if (!epics?.length) return null;

  const allSelected = selected.length === epics.length;
  const toggleAll   = () => onChange(allSelected ? [] : epics.map(e => e.db_id).filter(Boolean));
  const toggle      = (id) =>
    onChange(selected.includes(id) ? selected.filter(x => x !== id) : [...selected, id]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-slate-600">Sélectionnez les epics à corriger :</p>
        <button onClick={toggleAll} className="text-xs text-cyan hover:underline">
          {allSelected ? "Tout désélectionner" : "Tout sélectionner"}
        </button>
      </div>
      <div className="space-y-1 max-h-52 overflow-y-auto pr-1">
        {epics.map((epic, i) => {
          const id = epic.db_id;
          if (!id) return null;
          const checked = selected.includes(id);
          return (
            <label
              key={id}
              className={clsx(
                "flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-colors",
                checked
                  ? "bg-navy/5 border-navy/30"
                  : "bg-slate-50 border-slate-200 hover:border-slate-300"
              )}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(id)}
                className="mt-0.5 accent-navy shrink-0"
              />
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="w-5 h-5 rounded bg-navy text-white text-xs font-bold flex items-center justify-center shrink-0">
                    {i + 1}
                  </span>
                  <span className="text-xs font-medium text-navy truncate">{epic.title}</span>
                </div>
                {epic.description && (
                  <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">{epic.description}</p>
                )}
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}

// ── Sélecteur de stories (phase "stories") ────────────────────
function StoriesSelector({ stories, epics, selected, onChange }) {
  const [closedEpics, setClosedEpics] = useState(new Set());

  const grouped = useMemo(() => {
    const g = {};
    (stories ?? []).forEach(s => {
      const key = s.epic_id ?? 0;
      if (!g[key]) g[key] = [];
      g[key].push(s);
    });
    return g;
  }, [stories]);

  if (!stories?.length) return null;

  const allIds      = stories.map(s => s.db_id).filter(Boolean);
  const allSelected = allIds.length > 0 && allIds.every(id => selected.includes(id));

  const toggleAll   = () => onChange(allSelected ? [] : [...allIds]);
  const toggleStory = (id) =>
    onChange(selected.includes(id) ? selected.filter(x => x !== id) : [...selected, id]);
  const toggleEpic  = (epicIdx) => {
    const epicStories = (grouped[epicIdx] ?? []).map(s => s.db_id).filter(Boolean);
    const allIn = epicStories.every(id => selected.includes(id));
    onChange(allIn
      ? selected.filter(id => !epicStories.includes(id))
      : [...new Set([...selected, ...epicStories])]
    );
  };
  const toggleCollapse = (epicIdx) =>
    setClosedEpics(prev => {
      const next = new Set(prev);
      next.has(epicIdx) ? next.delete(epicIdx) : next.add(epicIdx);
      return next;
    });

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-slate-600">
          Sélectionnez les stories à corriger :
        </p>
        <button onClick={toggleAll} className="text-xs text-cyan hover:underline">
          {allSelected ? "Tout désélectionner" : "Tout sélectionner"}
        </button>
      </div>

      <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
        {Object.entries(grouped).map(([epicIdx, epicStories]) => {
          const epicInfo  = epics?.[parseInt(epicIdx)];
          const epicIds   = epicStories.map(s => s.db_id).filter(Boolean);
          const allIn     = epicIds.length > 0 && epicIds.every(id => selected.includes(id));
          const someIn    = epicIds.some(id => selected.includes(id));
          const isOpen    = !closedEpics.has(epicIdx);
          const Chevron   = isOpen ? ChevronDown : ChevronRight;

          return (
            <div key={epicIdx} className="border border-slate-200 rounded-lg overflow-hidden">
              {/* Header epic */}
              <div className="flex items-center gap-2 px-3 py-2 bg-slate-50">
                <input
                  type="checkbox"
                  checked={allIn}
                  ref={el => { if (el) el.indeterminate = someIn && !allIn; }}
                  onChange={() => toggleEpic(epicIdx)}
                  className="accent-navy shrink-0"
                />
                <button
                  onClick={() => toggleCollapse(epicIdx)}
                  className="flex items-center gap-1.5 flex-1 text-left"
                >
                  <Chevron size={12} className="text-slate-400 shrink-0" />
                  <span className="w-5 h-5 rounded bg-navy text-white text-xs font-bold flex items-center justify-center shrink-0">
                    {parseInt(epicIdx) + 1}
                  </span>
                  <span className="text-xs font-semibold text-navy truncate flex-1">
                    {epicInfo?.title ?? `Epic ${parseInt(epicIdx) + 1}`}
                  </span>
                  <span className="text-xs text-slate-400 shrink-0">
                    {epicStories.length} stories
                  </span>
                </button>
              </div>

              {/* Stories de l'epic */}
              {isOpen && (
                <div className="divide-y divide-slate-100">
                  {epicStories.map((story, si) => {
                    if (!story.db_id) return null;
                    const checked = selected.includes(story.db_id);
                    return (
                      <label
                        key={story.db_id}
                        className={clsx(
                          "flex items-start gap-2.5 px-3 py-2 cursor-pointer transition-colors",
                          checked ? "bg-violet-50" : "bg-white hover:bg-slate-50"
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleStory(story.db_id)}
                          className="mt-0.5 accent-violet-600 shrink-0"
                        />
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-slate-700 leading-snug">
                            {story.title}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-slate-400">
                              {story.story_points ?? "?"} pts
                            </span>
                            {parseAC(story.acceptance_criteria).length > 0 && (
                              <span className="text-xs text-slate-400">
                                · {parseAC(story.acceptance_criteria).length} critères
                              </span>
                            )}
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// COMPOSANT PRINCIPAL
// ══════════════════════════════════════════════════════════════

export default function ValidationCard({ onValidate, phase, aiOutput }) {
  const [feedback,       setFeedback]       = useState("");
  const [showReject,     setShowReject]      = useState(false);
  const [showSelector,   setShowSelector]    = useState(false);
  const [selectedStories, setSelectedStories] = useState([]);
  const [selectedEpics,   setSelectedEpics]   = useState([]);
  const [submitting,     setSubmitting]      = useState(false);
  const [error,          setError]           = useState(null);

  const isStoriesPhase = phase === "stories";
  const isEpicsPhase   = phase === "epics";
  const hasSelector    = isStoriesPhase || isEpicsPhase;

  const stories = aiOutput?.stories ?? [];
  const epics   = aiOutput?.epics   ?? [];

  const selectedCount = isStoriesPhase ? selectedStories.length : selectedEpics.length;

  const handleValidate = async (approved) => {
    if (!approved && !showReject) { setShowReject(true); return; }
    if (!approved && !feedback.trim()) return;

    setSubmitting(true);
    setError(null);
    try {
      await onValidate(
        approved,
        feedback || null,
        isStoriesPhase && selectedStories.length ? selectedStories : null,
        isEpicsPhase   && selectedEpics.length   ? selectedEpics   : null,
      );
      setFeedback("");
      setShowReject(false);
      setShowSelector(false);
      setSelectedStories([]);
      setSelectedEpics([]);
    } catch (e) {
      setError(e.response?.data?.detail || "Erreur lors de la validation.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = () => {
    setShowReject(false);
    setShowSelector(false);
    setFeedback("");
    setSelectedStories([]);
    setSelectedEpics([]);
    setError(null);
  };

  return (
    <div className="card p-5 border-2 border-amber-200">
      <div className="flex items-center gap-2 mb-4">
        <Zap size={16} className="text-amber-500" />
        <h3 className="font-medium text-slate-800 text-sm">Votre validation est requise</h3>
      </div>

      {/* ── Formulaire de rejet ─────────────────────────────── */}
      {showReject && (
        <div className="mb-4 space-y-3">

          {/* Feedback texte (obligatoire) */}
          <div>
            <label className="text-xs font-medium text-slate-600 block mb-1.5">
              Feedback pour l'IA <span className="text-red-500">(obligatoire)</span>
            </label>
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder={
                isStoriesPhase
                  ? "Ex: Les stories 2 et 5 manquent de critères d'acceptation..."
                  : isEpicsPhase
                  ? "Ex: L'epic 3 est trop large, découpez-le en 2..."
                  : "Ex: Les epics sont trop larges, découpez davantage..."
              }
              rows={3}
              className="w-full text-sm border border-slate-200 rounded-xl px-3 py-2.5
                         focus:outline-none focus:ring-2 focus:ring-amber-200
                         focus:border-amber-400 resize-none"
            />
          </div>

          {/* Sélecteur ciblé (optionnel) */}
          {hasSelector && (
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <button
                onClick={() => setShowSelector(v => !v)}
                className="w-full flex items-center gap-2 px-3 py-2.5 bg-slate-50
                           hover:bg-slate-100 transition-colors text-left"
              >
                <Target size={13} className="text-cyan shrink-0" />
                <span className="text-xs font-medium text-slate-700 flex-1">
                  Cibler des éléments spécifiques
                  {selectedCount > 0 && (
                    <span className="ml-2 bg-cyan text-white text-xs px-1.5 py-0.5 rounded-full">
                      {selectedCount} sélectionné{selectedCount > 1 ? "s" : ""}
                    </span>
                  )}
                </span>
                <span className="text-xs text-slate-400">
                  {showSelector ? "Masquer" : "Afficher"}
                </span>
              </button>

              {showSelector && (
                <div className="px-3 py-3 border-t border-slate-200">
                  <p className="text-xs text-slate-400 mb-3">
                    Optionnel — si rien n'est coché, le feedback s'applique à tout.
                  </p>
                  {isStoriesPhase && (
                    <StoriesSelector
                      stories={stories}
                      epics={epics}
                      selected={selectedStories}
                      onChange={setSelectedStories}
                    />
                  )}
                  {isEpicsPhase && (
                    <EpicsSelector
                      epics={epics}
                      selected={selectedEpics}
                      onChange={setSelectedEpics}
                    />
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700
                        text-xs rounded-xl px-3 py-2 mb-3">
          <AlertCircle size={13} className="shrink-0" /> {error}
        </div>
      )}

      <div className="flex gap-3">
        {/* Rejeter */}
        <button
          onClick={() => showReject ? handleValidate(false) : setShowReject(true)}
          disabled={submitting || (showReject && !feedback.trim())}
          className={clsx(
            "flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all",
            "border border-red-200 text-red-600 hover:bg-red-50",
            (submitting || (showReject && !feedback.trim())) && "opacity-50 cursor-not-allowed",
          )}
        >
          <ThumbsDown size={15} />
          {showReject
            ? selectedCount > 0
              ? `Corriger ${selectedCount} élément${selectedCount > 1 ? "s" : ""}`
              : "Confirmer le rejet"
            : "Rejeter"
          }
        </button>

        {/* Annuler (si modal ouvert) */}
        {showReject && (
          <button
            onClick={handleCancel}
            className="px-3 py-2.5 rounded-xl text-sm text-slate-500 hover:text-slate-700
                       hover:bg-slate-100 transition-all"
          >
            Annuler
          </button>
        )}

        {/* Approuver */}
        <button
          onClick={() => handleValidate(true)}
          disabled={submitting}
          className={clsx(
            "flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl",
            "text-sm font-medium transition-all bg-navy text-white hover:bg-navy/90",
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
