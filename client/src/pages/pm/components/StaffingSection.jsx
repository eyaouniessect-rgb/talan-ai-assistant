import { useState, useEffect, useRef } from "react";
import {
  CheckCircle, Clock, Loader, ChevronDown, ChevronRight,
  User, Wrench, TrendingUp, Zap, AlertCircle, RefreshCw,
  Pencil, X, Check, Save, Calendar, Users,
} from "lucide-react";
import clsx from "clsx";
import {
  getProjectStories, updateStaffingProfiles,
  getStaffingAvailableProfiles, getStaffingAvailableSkills,
  updateNormalizationDecisions, restartStaffing,
  updateSprintCapacities,
} from "../../../api/pipeline";
import MatchingResultCard from "./MatchingResultCard";

// ── Définition des 6 sous-étapes ──────────────────────────────
const SUB_STEPS = [
  {
    key:   "profile_extraction",
    label: "Extraction des profils",
    icon:  User,
    desc:  "Analyse des user stories pour extraire les profils et compétences requis",
  },
  {
    key:   "profile_normalization",
    label: "Normalisation des profils",
    icon:  Wrench,
    desc:  "Correspondance des profils requis avec les intitulés de poste réels en base",
  },
  {
    key:   "story_distribution",
    label: "Répartition initiale",
    icon:  Calendar,
    desc:  "Répartition provisoire des user stories dans les fenêtres de sprint",
  },
  {
    key:   "candidate_filtering",
    label: "Filtrage des candidats",
    icon:  Users,
    desc:  "Recherche des collaborateurs 100% disponibles par sprint",
  },
  {
    key:   "matching",
    label: "Matching stories / équipe",
    icon:  Zap,
    desc:  "Affectation intelligente de chaque story au meilleur collaborateur",
  },
  {
    key:   "velocity_feasibility",
    label: "Vélocité & Faisabilité",
    icon:  TrendingUp,
    desc:  "Calcul de la vélocité estimée et analyse de la faisabilité de la deadline",
  },
];

// ── Badge statut ───────────────────────────────────────────────
function StepStatusBadge({ status }) {
  if (status === "done")
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-green-600 bg-green-50 px-2 py-0.5 rounded-full border border-green-200">
        <CheckCircle size={10} /> Terminé
      </span>
    );
  if (status === "running")
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200">
        <Loader size={10} className="animate-spin" /> En cours
      </span>
    );
  if (status === "error")
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-red-600 bg-red-50 px-2 py-0.5 rounded-full border border-red-200">
        <AlertCircle size={10} /> Erreur
      </span>
    );
  return (
    <span className="flex items-center gap-1 text-xs font-medium text-slate-400 bg-slate-50 px-2 py-0.5 rounded-full border border-slate-200">
      <Clock size={10} /> En attente
    </span>
  );
}

// ── Badge niveau ───────────────────────────────────────────────
const LEVEL_STYLE = {
  JUNIOR: "bg-green-100  text-green-700  border-green-200",
  MID:    "bg-blue-100   text-blue-700   border-blue-200",
  SENIOR: "bg-purple-100 text-purple-700 border-purple-200",
};

function LevelBadge({ level }) {
  return (
    <span className={clsx(
      "text-xs font-semibold px-2 py-0.5 rounded-full border",
      LEVEL_STYLE[level] ?? "bg-slate-100 text-slate-500 border-slate-200"
    )}>
      {level ?? "MID"}
    </span>
  );
}

// ── Sélecteur de tags (profils ou compétences) ─────────────────
function TagSelector({ tags, onAdd, onRemove, options, placeholder, chipClass }) {
  const [input, setInput] = useState("");
  const [open,  setOpen]  = useState(false);
  const ref     = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = options
    .filter((o) => !tags.includes(o) && (!input || o.toLowerCase().includes(input.toLowerCase())))
    .slice(0, 30);

  const addCustom = () => {
    const val = input.trim();
    if (val && !tags.includes(val)) { onAdd(val); setInput(""); }
  };

  const toggleOpen = () => {
    setOpen((v) => !v);
    if (!open) inputRef.current?.focus();
  };

  return (
    <div ref={ref} className="space-y-1.5">
      {/* Tags existants */}
      <div className="flex flex-wrap gap-1 min-h-[24px]">
        {tags.map((tag) => (
          <span
            key={tag}
            className={clsx(
              "inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border font-medium",
              chipClass
            )}
          >
            {tag}
            <button
              type="button"
              onClick={() => onRemove(tag)}
              className="hover:text-red-500 transition-colors ml-0.5"
            >
              <X size={9} />
            </button>
          </span>
        ))}
        {tags.length === 0 && (
          <span className="text-xs text-slate-300 italic">Aucun</span>
        )}
      </div>

      {/* Input + bouton dropdown + liste */}
      <div className="relative">
        <div className="flex items-center border border-slate-200 rounded-lg bg-white overflow-hidden focus-within:border-blue-400">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => { setInput(e.target.value); setOpen(true); }}
            onFocus={() => setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); addCustom(); }
              if (e.key === "Escape") setOpen(false);
            }}
            placeholder={placeholder}
            className="flex-1 text-xs px-2.5 py-1.5 bg-transparent focus:outline-none"
          />
          {/* Bouton chevron — ouvre la liste complète */}
          <button
            type="button"
            onMouseDown={(e) => { e.preventDefault(); toggleOpen(); }}
            className="px-2 text-slate-400 hover:text-slate-600 transition-colors border-l border-slate-100"
          >
            <ChevronDown size={12} className={clsx("transition-transform", open && "rotate-180")} />
          </button>
        </div>

        {/* Liste déroulante */}
        {open && (
          <div className="absolute top-full left-0 right-0 mt-0.5 bg-white border border-slate-200 rounded-lg shadow-lg z-30 max-h-48 overflow-y-auto">
            {filtered.length === 0 && !input.trim() && (
              <p className="text-xs text-slate-400 italic px-3 py-2">
                {options.length === 0 ? "Chargement…" : "Toutes les options déjà sélectionnées"}
              </p>
            )}
            {filtered.map((opt) => (
              <button
                key={opt}
                type="button"
                onMouseDown={(e) => { e.preventDefault(); onAdd(opt); setInput(""); }}
                className="w-full text-left text-xs px-3 py-2 hover:bg-slate-50 transition-colors"
              >
                {opt}
              </button>
            ))}
            {input.trim() && !options.map((o) => o.toLowerCase()).includes(input.trim().toLowerCase()) && (
              <button
                type="button"
                onMouseDown={(e) => { e.preventDefault(); addCustom(); setOpen(false); }}
                className="w-full text-left text-xs px-3 py-2 hover:bg-blue-50 text-blue-600 border-t border-slate-100 font-medium"
              >
                + Ajouter &ldquo;{input.trim()}&rdquo;
              </button>
            )}
            {filtered.length === 0 && input.trim() && options.map((o) => o.toLowerCase()).includes(input.trim().toLowerCase()) && (
              <p className="text-xs text-slate-400 italic px-3 py-2">Déjà sélectionné</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const PAGE_SIZE = 5;

// ── Badges correspondance normalisation ───────────────────────
const MATCH_TYPE_STYLE = {
  exact: { bg: "bg-green-100  text-green-700  border-green-200", label: "Exact" },
  close: { bg: "bg-amber-100  text-amber-700  border-amber-200", label: "Proche" },
  none:  { bg: "bg-red-100    text-red-600    border-red-200",   label: "Aucun match" },
};

function MatchTypeBadge({ type }) {
  const s = MATCH_TYPE_STYLE[type] ?? MATCH_TYPE_STYLE.none;
  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${s.bg}`}>
      {s.label}
    </span>
  );
}

// ── Résultat du Step 2 : Profile Normalization ────────────────
function ProfileNormalizationResult({ result, projectId }) {
  const mappings        = result?.profile_mappings     ?? [];
  const availableTitles = result?.available_job_titles ?? [];
  const [decisions, setDecisions] = useState(result?.pm_decisions ?? {});
  const [saving,    setSaving]    = useState(false);
  const [saveError, setSaveError] = useState(null);

  useEffect(() => {
    setDecisions(result?.pm_decisions ?? {});
  }, [result]);

  if (!mappings.length)
    return (
      <p className="text-sm text-slate-400 italic text-center py-4">
        Aucun résultat de normalisation disponible.
      </p>
    );

  const acceptCount  = Object.values(decisions).filter((d) => d === "accept").length;
  const recruitCount = Object.values(decisions).filter((d) => d === "recruit").length;

  const toggle = async (profile) => {
    const next = { ...decisions, [profile]: decisions[profile] === "accept" ? "recruit" : "accept" };
    setDecisions(next);
    setSaving(true);
    setSaveError(null);
    try {
      await updateNormalizationDecisions(projectId, next);
    } catch (e) {
      setSaveError(e?.response?.data?.detail ?? "Erreur lors de la sauvegarde.");
      setDecisions(decisions); // rollback
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-slate-50 rounded-xl p-3 text-center">
          <div className="font-bold text-xl text-navy">{mappings.length}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Profils</div>
        </div>
        <div className="bg-green-50 rounded-xl p-3 text-center">
          <div className="font-bold text-xl text-green-700">{acceptCount}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Chercher en base</div>
        </div>
        <div className="bg-orange-50 rounded-xl p-3 text-center">
          <div className="font-bold text-xl text-orange-600">{recruitCount}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">À recruter</div>
        </div>
      </div>

      {/* Info intitulés en base */}
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 space-y-1.5">
        <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
          {availableTitles.length} intitulés de poste en base
        </p>
        <div className="flex flex-wrap gap-1.5">
          {availableTitles.slice(0, 20).map((t) => (
            <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-600">
              {t}
            </span>
          ))}
          {availableTitles.length > 20 && (
            <span className="text-[10px] text-slate-400 italic">+{availableTitles.length - 20} autres</span>
          )}
        </div>
      </div>

      {saveError && (
        <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 border border-red-200">
          {saveError}
        </p>
      )}

      {/* Table des mappings */}
      <div className="rounded-xl border border-slate-200 overflow-hidden">
        <div className="grid grid-cols-[1.4fr_1.6fr_120px_90px_150px] gap-2 px-4 py-2.5 bg-slate-50 border-b border-slate-200 text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
          <span>Profil requis</span>
          <span>Intitulés matchés</span>
          <span className="text-center">Correspondance</span>
          <span className="text-center">Confiance</span>
          <span className="text-center">Décision PM</span>
        </div>
        <div className="divide-y divide-slate-100 bg-white">
          {mappings.map((m) => {
            const decision = decisions[m.required_profile] ?? "accept";
            const isRecruit = decision === "recruit";
            return (
              <div
                key={m.required_profile}
                className={clsx(
                  "grid grid-cols-[1.4fr_1.6fr_120px_90px_150px] gap-2 px-4 py-3 items-center",
                  isRecruit && "bg-orange-50/40"
                )}
              >
                {/* Profil requis */}
                <div>
                  <p className="text-sm font-semibold text-slate-800">{m.required_profile}</p>
                  {m.reason && (
                    <p className="text-[10px] text-slate-400 mt-0.5 leading-snug">{m.reason}</p>
                  )}
                </div>

                {/* Intitulés matchés */}
                <div className="flex flex-wrap gap-1">
                  {m.matched_job_titles?.length > 0
                    ? m.matched_job_titles.map((t) => (
                        <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-navy/10 text-navy border border-navy/15 font-medium">
                          {t}
                        </span>
                      ))
                    : <span className="text-xs text-slate-400 italic">—</span>
                  }
                </div>

                {/* Correspondance */}
                <div className="flex justify-center">
                  <MatchTypeBadge type={m.match_type} />
                </div>

                {/* Confiance */}
                <div className="flex flex-col items-center gap-1">
                  <span className="text-sm font-bold text-slate-700">{Math.round(m.confidence * 100)}%</span>
                  <div className="w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className={clsx(
                        "h-full rounded-full",
                        m.confidence >= 0.9 ? "bg-green-500" :
                        m.confidence >= 0.7 ? "bg-amber-400" : "bg-red-400"
                      )}
                      style={{ width: `${m.confidence * 100}%` }}
                    />
                  </div>
                </div>

                {/* Décision PM — 2 boutons toujours visibles */}
                <div className="flex flex-col gap-1 items-center">
                  {/* Bouton "Utiliser le profil trouvé" */}
                  <button
                    type="button"
                    disabled={saving || m.match_type === "none"}
                    onClick={() => !isRecruit || toggle(m.required_profile)}
                    className={clsx(
                      "w-full text-xs font-semibold px-2.5 py-1.5 rounded-lg border transition-colors",
                      !isRecruit
                        ? "bg-green-500 text-white border-green-600 shadow-sm"
                        : "bg-white text-slate-400 border-slate-200 hover:border-green-300 hover:text-green-600",
                      (saving || m.match_type === "none") && "opacity-40 cursor-not-allowed"
                    )}
                    title={m.match_type === "none" ? "Aucun profil correspondant en base" : "Utiliser les intitulés matchés pour chercher en interne"}
                  >
                    ✓ Utiliser le profil trouvé
                  </button>

                  {/* Bouton "À Recruter" */}
                  <button
                    type="button"
                    disabled={saving || m.match_type === "exact"}
                    onClick={() => isRecruit || toggle(m.required_profile)}
                    className={clsx(
                      "w-full text-xs font-semibold px-2.5 py-1.5 rounded-lg border transition-colors",
                      isRecruit
                        ? "bg-orange-500 text-white border-orange-600 shadow-sm"
                        : "bg-white text-slate-400 border-slate-200 hover:border-orange-300 hover:text-orange-600",
                      (saving || m.match_type === "exact") && "opacity-40 cursor-not-allowed"
                    )}
                    title={m.match_type === "exact" ? "Profil exact trouvé en base — recrutement inutile" : "Déclarer ce profil comme besoin de recrutement"}
                  >
                    🔍 À Recruter
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {saving && (
        <p className="text-xs text-blue-500 text-center flex items-center justify-center gap-1">
          <Loader size={10} className="animate-spin" /> Sauvegarde en cours…
        </p>
      )}
    </div>
  );
}

// ── Résultat du Step 1 : Profile Extraction ───────────────────
function ProfileExtractionResult({ result, storyMap, loading, projectId }) {
  const profiles = result?.stories_profiles ?? [];

  const [editedProfiles, setEditedProfiles] = useState(profiles);
  const [editingId,      setEditingId]      = useState(null);
  const [expanded,       setExpanded]       = useState(new Set());
  const [dbProfiles,     setDbProfiles]     = useState([]);
  const [dbSkills,       setDbSkills]       = useState([]);
  const [saving,         setSaving]         = useState(false);
  const [saveError,      setSaveError]      = useState(null);
  const [filterLevel,    setFilterLevel]    = useState("ALL");
  const [page,           setPage]           = useState(1);

  useEffect(() => {
    setEditedProfiles(result?.stories_profiles ?? []);
  }, [result]);

  useEffect(() => {
    getStaffingAvailableProfiles().then(setDbProfiles).catch(() => {});
    getStaffingAvailableSkills().then(setDbSkills).catch(() => {});
  }, []);

  // Remettre à la page 1 quand le filtre change
  useEffect(() => { setPage(1); }, [filterLevel]);

  if (!profiles.length)
    return (
      <p className="text-sm text-slate-400 italic text-center py-4">
        Aucun résultat d'extraction disponible.
      </p>
    );

  const toggleExpand = (id) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const getEdited  = (storyId) => editedProfiles.find((p) => p.story_id === storyId);

  const updateField = (storyId, field, value) =>
    setEditedProfiles((prev) =>
      prev.map((p) => (p.story_id === storyId ? { ...p, [field]: value } : p))
    );

  const addTag = (storyId, field, val) => {
    const p = getEdited(storyId);
    if (!p || (p[field] ?? []).includes(val)) return;
    updateField(storyId, field, [...(p[field] ?? []), val]);
  };

  const removeTag = (storyId, field, val) => {
    const p = getEdited(storyId);
    if (!p) return;
    updateField(storyId, field, (p[field] ?? []).filter((x) => x !== val));
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await updateStaffingProfiles(projectId, editedProfiles);
      setEditingId(null);
    } catch (e) {
      setSaveError(e?.response?.data?.detail ?? "Erreur lors de la sauvegarde.");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = (storyId) => {
    const orig = profiles.find((p) => p.story_id === storyId);
    if (orig) setEditedProfiles((prev) => prev.map((p) => (p.story_id === storyId ? { ...orig } : p)));
    setEditingId(null);
    setSaveError(null);
  };

  // ── Calculs statistiques ────────────────────────────────────
  const juniorCount = editedProfiles.filter((p) => p.required_level === "JUNIOR").length;
  const midCount    = editedProfiles.filter((p) => p.required_level === "MID").length;
  const seniorCount = editedProfiles.filter((p) => p.required_level === "SENIOR").length;

  // Top 4 profils (par fréquence d'apparition)
  const profileFreq = {};
  editedProfiles.forEach((p) => (p.required_profiles ?? []).forEach((prof) => {
    profileFreq[prof] = (profileFreq[prof] ?? 0) + 1;
  }));
  const top4Profiles = Object.entries(profileFreq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);

  // Skills agrégées (triées par fréquence)
  const skillFreq = {};
  editedProfiles.forEach((p) => (p.required_skills ?? []).forEach((sk) => {
    skillFreq[sk] = (skillFreq[sk] ?? 0) + 1;
  }));
  const topSkills = Object.entries(skillFreq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);

  // ── Filtre + pagination ─────────────────────────────────────
  const filtered  = filterLevel === "ALL"
    ? editedProfiles
    : editedProfiles.filter((p) => p.required_level === filterLevel);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated  = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="space-y-4">

      {/* ── Statistiques niveau ─────────────────────────────── */}
      <div className="grid grid-cols-5 gap-2">
        {[
          { label: "Total",   value: editedProfiles.length, color: "text-navy",        bg: "bg-slate-50" },
          { label: "JUNIOR",  value: juniorCount,           color: "text-green-700",   bg: "bg-green-50" },
          { label: "MID",     value: midCount,              color: "text-blue-700",    bg: "bg-blue-50"  },
          { label: "SENIOR",  value: seniorCount,           color: "text-purple-700",  bg: "bg-purple-50"},
          { label: "Profils", value: Object.keys(profileFreq).length, color: "text-orange-600", bg: "bg-orange-50" },
        ].map(({ label, value, color, bg }) => (
          <div key={label} className={`${bg} rounded-xl p-3 text-center`}>
            <div className={`font-bold text-xl ${color}`}>{value}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* ── Top 4 profils ───────────────────────────────────── */}
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 space-y-2">
        <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">Top 4 profils extraits</p>
        <div className="flex flex-wrap gap-2">
          {top4Profiles.map(([prof, count]) => (
            <span key={prof} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-navy/10 text-navy font-medium border border-navy/15">
              {prof}
              <span className="bg-navy/20 text-navy text-[10px] font-bold px-1.5 py-0.5 rounded-full">{count}</span>
            </span>
          ))}
          {top4Profiles.length === 0 && <span className="text-xs text-slate-400 italic">Aucun profil</span>}
        </div>
      </div>

      {/* ── Skills agrégées du projet ────────────────────────── */}
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 space-y-2">
        <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">Compétences agrégées du projet</p>
        <div className="flex flex-wrap gap-1.5">
          {topSkills.map(([skill, count]) => (
            <span key={skill} className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-cyan/10 text-cyan-700 border border-cyan/20 font-medium">
              {skill}
              <span className="text-[9px] text-cyan-500 font-bold">×{count}</span>
            </span>
          ))}
          {topSkills.length === 0 && <span className="text-xs text-slate-400 italic">Aucune compétence</span>}
        </div>
      </div>

      {/* Erreur de sauvegarde */}
      {saveError && (
        <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 border border-red-200">
          {saveError}
        </p>
      )}

      {/* ── Filtre par séniorité ─────────────────────────────── */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-500 font-medium">Filtrer :</span>
        {[
          { key: "ALL",    label: "Tous",   color: "bg-slate-100 text-slate-600 hover:bg-slate-200", active: "bg-slate-700 text-white" },
          { key: "JUNIOR", label: "Junior", color: "bg-green-50 text-green-700 hover:bg-green-100",  active: "bg-green-600 text-white" },
          { key: "MID",    label: "Mid",    color: "bg-blue-50 text-blue-700 hover:bg-blue-100",     active: "bg-blue-600 text-white"  },
          { key: "SENIOR", label: "Senior", color: "bg-purple-50 text-purple-700 hover:bg-purple-100", active: "bg-purple-600 text-white" },
        ].map(({ key, label, color, active }) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilterLevel(key)}
            className={clsx(
              "text-xs font-medium px-3 py-1 rounded-full transition-colors",
              filterLevel === key ? active : color
            )}
          >
            {label}
            {key !== "ALL" && (
              <span className="ml-1 opacity-70">
                ({key === "JUNIOR" ? juniorCount : key === "MID" ? midCount : seniorCount})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Tableau paginé ───────────────────────────────────── */}
      <div className="rounded-xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-[1fr_160px_80px_32px] gap-2 px-4 py-2.5 bg-slate-50 border-b border-slate-200 text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
          <span>Story</span>
          <span>Profils requis</span>
          <span className="text-center">Niveau</span>
          <span />
        </div>

        {/* Lignes */}
        <div className="divide-y divide-slate-100 bg-white">
          {paginated.length === 0 && (
            <p className="text-sm text-slate-400 italic text-center py-6">
              Aucune story pour ce niveau.
            </p>
          )}
          {paginated.map((p) => {
            const story     = storyMap[p.story_id];
            const isEditing = editingId === p.story_id;
            const isOpen    = expanded.has(p.story_id);
            const Chevron   = isOpen ? ChevronDown : ChevronRight;

            return (
              <div key={p.story_id}>
                {/* Ligne principale */}
                <div className="grid grid-cols-[1fr_160px_80px_32px] gap-2 px-4 py-3 items-center">
                  {/* Titre story */}
                  <button
                    type="button"
                    onClick={() => !isEditing && toggleExpand(p.story_id)}
                    className="flex items-start gap-1.5 min-w-0 text-left hover:text-slate-600 transition-colors"
                  >
                    {!isEditing && (
                      <Chevron size={13} className="text-slate-400 shrink-0 mt-0.5" />
                    )}
                    <div className="min-w-0">
                      {loading ? (
                        <div className="h-3 bg-slate-100 rounded w-3/4 animate-pulse" />
                      ) : story ? (
                        <p className="text-sm text-slate-800 font-medium leading-snug">
                          {story.title}
                        </p>
                      ) : (
                        <span className="text-xs text-slate-400 italic">
                          Story #{p.story_id}
                        </span>
                      )}
                      {story?.story_points != null && (
                        <span className="text-[10px] text-slate-400">
                          {story.story_points} SP
                        </span>
                      )}
                    </div>
                  </button>

                  {/* Profils requis (vue lecture) */}
                  {!isEditing ? (
                    <div className="flex flex-wrap gap-1">
                      {(p.required_profiles ?? []).map((prof) => (
                        <span
                          key={prof}
                          className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-navy/10 text-navy truncate max-w-[140px]"
                          title={prof}
                        >
                          {prof}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div /> /* remplacé par le panneau d'édition ci-dessous */
                  )}

                  {/* Niveau (vue lecture) */}
                  {!isEditing ? (
                    <div className="flex justify-center">
                      <LevelBadge level={p.required_level} />
                    </div>
                  ) : (
                    <div />
                  )}

                  {/* Bouton édition */}
                  <div className="flex justify-center">
                    {!isEditing ? (
                      <button
                        type="button"
                        onClick={() => { setEditingId(p.story_id); setExpanded((prev) => { const n = new Set(prev); n.delete(p.story_id); return n; }); }}
                        className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
                        title="Modifier"
                      >
                        <Pencil size={13} />
                      </button>
                    ) : null}
                  </div>
                </div>

                {/* ── Panneau d'édition inline ─────────────────── */}
                {isEditing && (
                  <div className="px-4 pb-4 pt-1 bg-blue-50/30 border-t border-blue-100 space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

                      {/* Niveau */}
                      <div>
                        <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide block mb-1.5">
                          Niveau requis
                        </label>
                        <select
                          value={p.required_level ?? "MID"}
                          onChange={(e) => updateField(p.story_id, "required_level", e.target.value)}
                          className="w-full text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 focus:border-blue-400 focus:outline-none bg-white font-medium"
                        >
                          <option value="JUNIOR">JUNIOR</option>
                          <option value="MID">MID</option>
                          <option value="SENIOR">SENIOR</option>
                        </select>
                      </div>

                      {/* Profils requis */}
                      <div>
                        <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide block mb-1.5">
                          Profils requis
                        </label>
                        <TagSelector
                          tags={p.required_profiles ?? []}
                          onAdd={(val) => addTag(p.story_id, "required_profiles", val)}
                          onRemove={(val) => removeTag(p.story_id, "required_profiles", val)}
                          options={dbProfiles}
                          placeholder="Rechercher ou saisir un profil…"
                          chipClass="bg-navy/10 text-navy border-navy/20"
                        />
                      </div>

                      {/* Compétences */}
                      <div>
                        <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide block mb-1.5">
                          Compétences requises
                        </label>
                        <TagSelector
                          tags={p.required_skills ?? []}
                          onAdd={(val) => addTag(p.story_id, "required_skills", val)}
                          onRemove={(val) => removeTag(p.story_id, "required_skills", val)}
                          options={dbSkills}
                          placeholder="Rechercher ou saisir une compétence…"
                          chipClass="bg-cyan/10 text-cyan-700 border-cyan/20"
                        />
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        type="button"
                        onClick={handleSave}
                        disabled={saving}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
                      >
                        {saving ? (
                          <Loader size={11} className="animate-spin" />
                        ) : (
                          <Save size={11} />
                        )}
                        {saving ? "Sauvegarde…" : "Sauvegarder"}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCancel(p.story_id)}
                        disabled={saving}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-600 text-xs font-medium hover:bg-slate-50 disabled:opacity-50 transition-colors"
                      >
                        <X size={11} />
                        Annuler
                      </button>
                    </div>
                  </div>
                )}

                {/* ── Skills dépliables (vue lecture) ─────────── */}
                {!isEditing && isOpen && (
                  <div className="px-10 pb-3 bg-slate-50/50 border-t border-slate-100">
                    <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mt-2 mb-1.5">
                      Compétences requises
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {(p.required_skills ?? []).map((skill) => (
                        <span
                          key={skill}
                          className="text-xs px-2 py-0.5 rounded-full bg-cyan/10 text-cyan-700 border border-cyan/20 font-medium"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Pagination ───────────────────────────────────────── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-1">
          <span className="text-xs text-slate-400">
            {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} sur {filtered.length} stories
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-2.5 py-1 rounded-lg text-xs font-medium border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              ← Préc
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setPage(n)}
                className={clsx(
                  "w-7 h-7 rounded-lg text-xs font-medium transition-colors",
                  n === page
                    ? "bg-navy text-white"
                    : "border border-slate-200 text-slate-600 hover:bg-slate-50"
                )}
              >
                {n}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-2.5 py-1 rounded-lg text-xs font-medium border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Suiv →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Résultat du Step 3 : Story Distribution ───────────────────
// Le PM peut ajuster la capacité cible (SP) de chaque sprint.
// Cliquer "Appliquer" → re-distribue les stories selon les nouvelles capacités.
function StoryDistributionResult({ result, projectId, project, onApplied }) {
  const sprints   = result?.sprints ?? [];
  const sprintDur = result?.sprint_duration_days ?? 10;

  // capacités éditables (état local synchronisé avec les capacités du résultat)
  const [editedCapacities, setEditedCapacities] = useState(
    () => sprints.map((s) => s.target_capacity_sp ?? 0)
  );
  const [applying,    setApplying]    = useState(false);
  const [applyError,  setApplyError]  = useState(null);
  const [open, setOpen] = useState(new Set([1]));

  // Resync si la prop result change (après application ou refetch)
  useEffect(() => {
    setEditedCapacities(sprints.map((s) => s.target_capacity_sp ?? 0));
  }, [result]);

  if (!sprints.length)
    return (
      <p className="text-sm text-slate-400 italic text-center py-4">
        Aucun résultat de répartition disponible.
      </p>
    );

  const totalSP    = result.total_story_points         ?? 0;
  const nbSprints  = result.number_of_sprints          ?? 0;

  const originalCapacities = sprints.map((s) => s.target_capacity_sp ?? 0);
  const hasChanges = editedCapacities.some((c, i) => c !== originalCapacities[i]);

  const configuredTotal = editedCapacities.reduce((sum, c) => sum + (Number(c) || 0), 0);
  const capacityGap     = configuredTotal - totalSP;
  // 0 = aligné, >0 = surplus (marge), <0 = déficit

  const toggleOpen = (n) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(n) ? next.delete(n) : next.add(n);
      return next;
    });

  const formatDate = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
  };

  const updateCapacity = (idx, value) => {
    const num = Math.max(1, parseInt(value, 10) || 1);
    setEditedCapacities((prev) => prev.map((c, i) => (i === idx ? num : c)));
  };

  const resetCapacities = () => {
    setEditedCapacities(originalCapacities);
    setApplyError(null);
  };

  const applyCapacities = async () => {
    setApplying(true);
    setApplyError(null);
    try {
      await updateSprintCapacities(projectId, editedCapacities);
      onApplied?.();
    } catch (e) {
      setApplyError(e?.response?.data?.detail ?? "Erreur lors de l'application des capacités.");
    } finally {
      setApplying(false);
    }
  };

  // Message capacité
  let gapBadge = null;
  if (capacityGap === 0) {
    gapBadge = (
      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700 border border-green-200">
        Aligné
      </span>
    );
  } else if (capacityGap > 0) {
    gapBadge = (
      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 border border-blue-200">
        +{capacityGap} marge
      </span>
    );
  } else {
    gapBadge = (
      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200">
        {capacityGap} déficit
      </span>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── En-tête synthèse projet ─────────────────────────────── */}
      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        <div className="grid grid-cols-3 md:grid-cols-6 divide-x divide-slate-100">
          <div className="px-3 py-2.5 text-center">
            <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Début</p>
            <p className="text-xs font-semibold text-slate-700 mt-0.5">{formatDate(project?.start_date)}</p>
          </div>
          <div className="px-3 py-2.5 text-center">
            <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Deadline</p>
            <p className="text-xs font-semibold text-slate-700 mt-0.5">{formatDate(project?.end_date)}</p>
          </div>
          <div className="px-3 py-2.5 text-center">
            <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Sprint</p>
            <p className="text-xs font-semibold text-slate-700 mt-0.5">{sprintDur} j.o.</p>
          </div>
          <div className="px-3 py-2.5 text-center">
            <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Sprints</p>
            <p className="text-xs font-semibold text-navy mt-0.5">{nbSprints}</p>
          </div>
          <div className="px-3 py-2.5 text-center">
            <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">SP backlog</p>
            <p className="text-xs font-semibold text-slate-700 mt-0.5">{totalSP}</p>
          </div>
          <div className="px-3 py-2.5 text-center">
            <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Capacité config.</p>
            <p className="text-xs font-semibold text-slate-700 mt-0.5">
              {configuredTotal}
              <span className="ml-1">{gapBadge}</span>
            </p>
          </div>
        </div>

        {/* Bandeau d'état capacité */}
        {capacityGap === 0 && (
          <div className="border-t border-green-100 bg-green-50 px-4 py-2 text-xs text-green-700 flex items-center gap-2">
            <CheckCircle size={12} className="shrink-0" />
            <span>Capacité alignée avec le backlog. La capacité configurée couvre exactement les story points du projet.</span>
          </div>
        )}
        {capacityGap > 0 && (
          <div className="border-t border-blue-100 bg-blue-50 px-4 py-2 text-xs text-blue-700 flex items-center gap-2">
            <CheckCircle size={12} className="shrink-0" />
            <span>
              Marge disponible de <strong>{capacityGap} SP</strong>. La capacité configurée dépasse le backlog —
              utilisable pour absorber des imprévus, du scope additionnel ou de la stabilisation.
            </span>
          </div>
        )}
        {capacityGap < 0 && (
          <div className="border-t border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700 flex items-center gap-2">
            <AlertCircle size={12} className="shrink-0" />
            <span>
              Capacité insuffisante de <strong>{Math.abs(capacityGap)} SP</strong>. La capacité configurée ne
              couvre pas entièrement le backlog ; certains sprints risquent d'être surchargés ou la deadline
              peut être difficile à respecter.
            </span>
          </div>
        )}
      </div>

      {/* ── Bandeau de modifications en attente + actions ───────── */}
      {hasChanges && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 flex items-center gap-3">
          <AlertCircle size={16} className="text-amber-600 shrink-0" />
          <p className="flex-1 text-xs text-amber-800">
            Des modifications sont en attente. Cliquez sur <strong>Appliquer la répartition</strong> pour
            recalculer l'affectation des stories selon les nouvelles capacités.
          </p>
          <button
            type="button"
            onClick={resetCapacities}
            disabled={applying}
            className="text-xs font-medium px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={applyCapacities}
            disabled={applying}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 transition-colors"
          >
            {applying ? <Loader size={11} className="animate-spin" /> : <Check size={11} />}
            {applying ? "Application…" : "Appliquer la répartition"}
          </button>
        </div>
      )}

      {applyError && (
        <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 border border-red-200">
          {applyError}
        </p>
      )}

      {/* ── Liste des sprints ───────────────────────────────────── */}
      <div className="space-y-2">
        {sprints.map((sprint, idx) => {
          const isOpen     = open.has(sprint.sprint_number);
          const editedCap  = editedCapacities[idx] ?? sprint.target_capacity_sp;
          const delta      = sprint.delta_sp ?? 0;
          const fillTarget = sprint.target_capacity_sp ?? 1;
          const fillPct    = Math.min(100, Math.round((sprint.actual_sp / fillTarget) * 100));
          const barColor   = Math.abs(delta) <= 3
            ? "bg-green-500"
            : delta > 0
            ? "bg-amber-400"
            : "bg-blue-400";

          return (
            <div
              key={sprint.sprint_number}
              className="rounded-xl border border-slate-200 overflow-hidden"
            >
              {/* Header sprint */}
              <div
                className="w-full flex items-center gap-3 px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors"
              >
                {/* Numéro */}
                <button
                  type="button"
                  onClick={() => toggleOpen(sprint.sprint_number)}
                  className="w-7 h-7 rounded-full bg-navy text-white text-xs font-bold flex items-center justify-center shrink-0"
                >
                  {sprint.sprint_number}
                </button>

                {/* Dates */}
                <button
                  type="button"
                  onClick={() => toggleOpen(sprint.sprint_number)}
                  className="flex-1 min-w-0 text-left"
                >
                  <p className="text-sm font-semibold text-slate-800">
                    Sprint {sprint.sprint_number}
                  </p>
                  <p className="text-[11px] text-slate-400">
                    {formatDate(sprint.start_date)} → {formatDate(sprint.end_date)}
                  </p>
                </button>

                {/* Capacité éditable */}
                <div className="flex items-center gap-1.5 shrink-0">
                  <span className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Cible</span>
                  <input
                    type="number"
                    min={1}
                    value={editedCap}
                    onChange={(e) => updateCapacity(idx, e.target.value)}
                    disabled={applying}
                    className={clsx(
                      "w-14 text-xs font-bold text-center px-1.5 py-1 rounded-lg border focus:outline-none transition-colors",
                      editedCap !== sprint.target_capacity_sp
                        ? "border-amber-400 bg-amber-50 text-amber-700"
                        : "border-slate-200 bg-white text-slate-700 focus:border-blue-400",
                    )}
                  />
                  <span className="text-[10px] text-slate-400 font-semibold">SP</span>
                </div>

                {/* Barre SP */}
                <div className="flex items-center gap-2 shrink-0">
                  <div className="w-20 h-2 rounded-full bg-slate-200 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${barColor}`}
                      style={{ width: `${fillPct}%` }}
                    />
                  </div>
                  <span className="text-xs font-bold text-slate-700 w-14 text-right">
                    {sprint.actual_sp} SP
                  </span>
                  {delta !== 0 && (
                    <span className={clsx(
                      "text-[10px] font-semibold px-1.5 py-0.5 rounded-full border",
                      delta > 0
                        ? "bg-amber-100 text-amber-700 border-amber-200"
                        : "bg-blue-100 text-blue-700 border-blue-200"
                    )}>
                      {delta > 0 ? "+" : ""}{delta} SP
                    </span>
                  )}
                  {delta === 0 && (
                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full border bg-green-100 text-green-700 border-green-200">
                      = cible
                    </span>
                  )}
                </div>

                {/* Chevron */}
                <button
                  type="button"
                  onClick={() => toggleOpen(sprint.sprint_number)}
                  className="text-slate-400 shrink-0"
                >
                  {isOpen
                    ? <ChevronDown size={14} />
                    : <ChevronRight size={14} />
                  }
                </button>
              </div>

              {/* Stories dépliables */}
              {isOpen && (
                <div className="divide-y divide-slate-100 bg-white">
                  {(sprint.assigned_stories ?? []).length === 0 ? (
                    <p className="text-xs text-slate-400 italic text-center py-3">
                      Aucune story affectée.
                    </p>
                  ) : (
                    (sprint.assigned_stories ?? []).map((story) => (
                      <div
                        key={story.story_id}
                        className="flex items-center gap-3 px-5 py-2.5"
                      >
                        <span className="text-[10px] font-bold text-slate-400 w-8 shrink-0 text-right">
                          #{story.rank}
                        </span>
                        <p className="flex-1 text-sm text-slate-700 leading-snug">
                          {story.title}
                        </p>
                        <span className="text-xs font-semibold text-navy bg-navy/10 px-2 py-0.5 rounded-full shrink-0">
                          {story.story_points} SP
                        </span>
                      </div>
                    ))
                  )}
                  {/* Footer SP */}
                  <div className="flex justify-between items-center px-5 py-2 bg-slate-50 text-[11px] text-slate-500">
                    <span>{(sprint.assigned_stories ?? []).length} story(s)</span>
                    <span className="font-semibold">
                      {sprint.actual_sp} / {sprint.target_capacity_sp} SP
                      {delta > 0 && <span className="text-amber-600 ml-1">(+{delta} dépassement)</span>}
                      {delta < 0 && <span className="text-blue-600 ml-1">({delta} sous-chargé)</span>}
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Résultat du Step 4 : Candidate Filtering (par sprint) ─────
// ── Carte d'un candidat (disponible ou indisponible) ─────────
function CandidateCard({ c }) {
  const isUnavailable = c.availability_status === "Unavailable";

  return (
    <div className={clsx(
      "flex items-start gap-3 px-5 py-3",
      isUnavailable && "bg-slate-50/60"
    )}>
      {/* Avatar */}
      <div className={clsx(
        "w-8 h-8 rounded-full text-xs font-bold flex items-center justify-center shrink-0 mt-0.5",
        isUnavailable ? "bg-slate-200 text-slate-400" : "bg-navy/10 text-navy"
      )}>
        {c.name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase()}
      </div>

      <div className="flex-1 min-w-0 space-y-1">
        {/* Nom + badges */}
        <div className="flex items-center gap-2 flex-wrap">
          <p className={clsx(
            "text-sm font-semibold",
            isUnavailable ? "text-slate-400" : "text-slate-800"
          )}>
            {c.name}
          </p>
          <LevelBadge level={c.seniority} />
          <MatchTypeBadge type={c.profile_match} />
          {isUnavailable ? (
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-red-100 text-red-600 border border-red-200">
              Indisponible
            </span>
          ) : (
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-700 border border-green-200">
              Disponible
            </span>
          )}
        </div>

        {/* Job title */}
        <p className="text-xs text-slate-500">{c.job_title}</p>

        {/* Raisons d'indisponibilité */}
        {isUnavailable && c.unavailable_periods?.length > 0 && (
          <div className="space-y-1 mt-1">
            {c.unavailable_periods.map((p, i) => (
              <div
                key={i}
                className={clsx(
                  "flex items-start gap-1.5 text-[11px] px-2 py-1.5 rounded-lg border",
                  p.reason_type === "leave"
                    ? "bg-amber-50 border-amber-200 text-amber-800"
                    : "bg-blue-50  border-blue-200  text-blue-800"
                )}
              >
                <span className="shrink-0 mt-px">
                  {p.reason_type === "leave" ? "🏖️" : "💼"}
                </span>
                <span className="leading-snug">{p.reason}</span>
              </div>
            ))}
          </div>
        )}

        {/* Skills (disponibles uniquement) */}
        {!isUnavailable && c.skills?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {c.skills.slice(0, 8).map((sk) => (
              <span
                key={sk}
                className="text-[10px] px-1.5 py-0.5 rounded-full bg-cyan/10 text-cyan-700 border border-cyan/20 font-medium"
              >
                {sk}
              </span>
            ))}
            {c.skills.length > 8 && (
              <span className="text-[10px] text-slate-400 italic">+{c.skills.length - 8}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function CandidateFilteringResult({ result }) {
  const candidatesBySprint = result?.candidates_by_sprint ?? {};
  const missingProfiles    = result?.missing_profiles     ?? [];
  const sprintKeys         = Object.keys(candidatesBySprint).sort();

  const [activeSprintKey,   setActiveSprintKey]   = useState(sprintKeys[0] ?? null);
  const [openProfiles,      setOpenProfiles]      = useState(new Set());
  const [showUnavailable,   setShowUnavailable]   = useState(new Set());

  useEffect(() => {
    if (!activeSprintKey && sprintKeys.length > 0) setActiveSprintKey(sprintKeys[0]);
  }, [sprintKeys]);

  if (!sprintKeys.length && !missingProfiles.length)
    return (
      <p className="text-sm text-slate-400 italic text-center py-4">
        Aucun résultat de filtrage disponible.
      </p>
    );

  const formatDate = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
  };

  const toggleProfile    = (key) =>
    setOpenProfiles((prev) => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });

  const toggleUnavailable = (key) =>
    setShowUnavailable((prev) => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });

  const activeSprint = activeSprintKey ? candidatesBySprint[activeSprintKey] : null;
  const profileKeys  = activeSprint
    ? Array.from(new Set([
        ...Object.keys(activeSprint.candidates_by_profile ?? {}),
        ...Object.keys(activeSprint.unavailable_candidates_by_profile ?? {}),
      ]))
    : [];

  return (
    <div className="space-y-4">
      {/* Profils à recruter */}
      {missingProfiles.length > 0 && (
        <div className="rounded-xl border border-orange-200 bg-orange-50 px-4 py-3">
          <p className="text-[11px] font-semibold text-orange-700 uppercase tracking-wide mb-2">
            {missingProfiles.length} profil(s) à recruter en externe
          </p>
          <div className="flex flex-wrap gap-1.5">
            {missingProfiles.map((p) => (
              <span key={p} className="text-xs font-medium px-2.5 py-1 rounded-full bg-orange-100 text-orange-700 border border-orange-200">
                {p}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Onglets sprint */}
      {sprintKeys.length > 0 && (
        <>
          <div className="flex gap-1.5 flex-wrap">
            {sprintKeys.map((key) => {
              const sp       = candidatesBySprint[key];
              const isActive = key === activeSprintKey;
              const unavailCount = Object.values(sp?.unavailable_candidates_by_profile ?? {})
                .reduce((s, arr) => s + arr.length, 0);
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => { setActiveSprintKey(key); setOpenProfiles(new Set()); setShowUnavailable(new Set()); }}
                  className={clsx(
                    "flex flex-col items-center px-3 py-2 rounded-xl border text-xs font-medium transition-colors",
                    isActive
                      ? "bg-navy text-white border-navy"
                      : "bg-white text-slate-600 border-slate-200 hover:border-navy/40 hover:text-navy"
                  )}
                >
                  <span className="font-bold">Sprint {sp?.sprint_number}</span>
                  <span className={clsx("text-[10px] mt-0.5", isActive ? "text-white/70" : "text-slate-400")}>
                    {formatDate(sp?.start_date)} → {formatDate(sp?.end_date)}
                  </span>
                  <div className="flex gap-1 mt-1">
                    <span className={clsx(
                      "text-[10px] font-semibold px-1.5 py-0.5 rounded-full",
                      isActive ? "bg-white/20 text-white" : "bg-green-100 text-green-700"
                    )}>
                      ✓ {sp?.total_available ?? 0}
                    </span>
                    {unavailCount > 0 && (
                      <span className={clsx(
                        "text-[10px] font-semibold px-1.5 py-0.5 rounded-full",
                        isActive ? "bg-white/20 text-white" : "bg-red-100 text-red-600"
                      )}>
                        ✗ {unavailCount}
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Contenu du sprint actif */}
          {activeSprint && (
            <div className="space-y-2">
              {profileKeys.length === 0 ? (
                <p className="text-sm text-slate-400 italic text-center py-6">
                  Aucun profil à rechercher pour ce sprint.
                </p>
              ) : (
                profileKeys.map((profile) => {
                  const available   = activeSprint.candidates_by_profile?.[profile]             ?? [];
                  const unavailable = activeSprint.unavailable_candidates_by_profile?.[profile] ?? [];
                  const profileKey  = `${activeSprintKey}_${profile}`;
                  const isOpen      = openProfiles.has(profileKey);
                  const showUnavail = showUnavailable.has(profileKey);

                  return (
                    <div key={profile} className="rounded-xl border border-slate-200 overflow-hidden">
                      {/* Header profil */}
                      <button
                        type="button"
                        onClick={() => toggleProfile(profileKey)}
                        className="w-full flex items-center gap-3 px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-slate-800">{profile}</p>
                        </div>

                        {/* Badges disponibles / indisponibles */}
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className={clsx(
                            "text-xs font-semibold px-2.5 py-1 rounded-full border",
                            available.length > 0
                              ? "bg-green-100 text-green-700 border-green-200"
                              : "bg-slate-100 text-slate-400 border-slate-200"
                          )}>
                            {available.length > 0 ? `✓ ${available.length}` : "Aucun"}
                          </span>
                          {unavailable.length > 0 && (
                            <span className="text-xs font-semibold px-2.5 py-1 rounded-full border bg-red-50 text-red-600 border-red-200">
                              ✗ {unavailable.length}
                            </span>
                          )}
                        </div>

                        {isOpen ? <ChevronDown size={14} className="text-slate-400 shrink-0" /> : <ChevronRight size={14} className="text-slate-400 shrink-0" />}
                      </button>

                      {/* Corps ouvert */}
                      {isOpen && (
                        <div className="bg-white">
                          {/* ── Disponibles ── */}
                          {available.length === 0 ? (
                            <p className="text-xs text-slate-400 italic text-center py-4 border-b border-slate-100">
                              Aucun collaborateur disponible pour ce sprint.
                            </p>
                          ) : (
                            <div className="divide-y divide-slate-100">
                              {available.map((c) => <CandidateCard key={c.employee_id} c={c} />)}
                            </div>
                          )}

                          {/* ── Indisponibles (section dépliable) ── */}
                          {unavailable.length > 0 && (
                            <div className="border-t border-slate-100">
                              <button
                                type="button"
                                onClick={() => toggleUnavailable(profileKey)}
                                className="w-full flex items-center gap-2 px-5 py-2.5 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
                              >
                                <span className="flex-1 text-xs font-semibold text-slate-500">
                                  {unavailable.length} collaborateur(s) indisponible(s) sur cette période
                                </span>
                                {showUnavail
                                  ? <ChevronDown  size={12} className="text-slate-400" />
                                  : <ChevronRight size={12} className="text-slate-400" />}
                              </button>
                              {showUnavail && (
                                <div className="divide-y divide-slate-100">
                                  {unavailable.map((c) => <CandidateCard key={c.employee_id} c={c} />)}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Bandeau dates de projet (durée totale) ───────────────────
function ProjectDurationBanner({ startDate, endDate }) {
  if (!startDate && !endDate) return null;

  const fmt = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" });
  };

  let durationLabel = null;
  if (startDate && endDate) {
    const start = new Date(startDate);
    const end   = new Date(endDate);
    const days  = Math.max(0, Math.round((end - start) / 86_400_000));
    const weeks = Math.round(days / 7);
    durationLabel = days < 7 ? `${days} j` : `${weeks} sem.`;
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 flex items-center gap-4">
      <div className="w-9 h-9 rounded-full bg-navy/10 text-navy flex items-center justify-center shrink-0">
        <Calendar size={16} />
      </div>
      <div className="flex-1 grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Début</p>
          <p className="text-sm font-semibold text-slate-700 mt-0.5">{fmt(startDate)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Durée</p>
          <p className="text-sm font-semibold text-navy mt-0.5">{durationLabel ?? "—"}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Deadline</p>
          <p className="text-sm font-semibold text-slate-700 mt-0.5">{fmt(endDate)}</p>
        </div>
      </div>
    </div>
  );
}

// ── Composant principal ───────────────────────────────────────
export default function StaffingSection({ aiOutput, projectId, project, onRefresh }) {
  const staffing = aiOutput?.staffing ?? {};
  const steps    = staffing?.steps    ?? {};

  const [storyMap,    setStoryMap]    = useState({});
  const [loading,     setLoading]     = useState(true);
  const [rerunning,   setRerunning]   = useState(false);
  const [rerunError,  setRerunError]  = useState(null);
  const [activeStep,  setActiveStep]  = useState(null);

  // Charger la map stories
  useEffect(() => {
    if (!projectId) { setLoading(false); return; }
    getProjectStories(projectId)
      .then((stories) => {
        const map = {};
        for (const s of stories) map[s.db_id] = s;
        setStoryMap(map);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [projectId]);

  // Sélection automatique : dernier step terminé (ou en erreur)
  // → s'avance automatiquement quand une nouvelle sous-étape se termine
  //   (sans bloquer la navigation manuelle vers une étape antérieure).
  const lastSeenDoneRef = useRef(null);

  useEffect(() => {
    // Priorité : step en erreur → toujours s'y déplacer
    const errorKey = SUB_STEPS.map((s) => s.key).reverse()
      .find((k) => steps[k]?.status === "error");
    if (errorKey) {
      if (activeStep !== errorKey) setActiveStep(errorKey);
      return;
    }

    const lastDoneKey = SUB_STEPS.map((s) => s.key).reverse()
      .find((k) => steps[k]?.status === "done");
    if (!lastDoneKey) return;

    // Initialisation OU nouveau step terminé → s'y déplacer automatiquement
    if (activeStep === null || lastDoneKey !== lastSeenDoneRef.current) {
      setActiveStep(lastDoneKey);
      lastSeenDoneRef.current = lastDoneKey;
    }
  }, [steps]);

  const handleRerun = async () => {
    setRerunning(true);
    setRerunError(null);
    try {
      await restartStaffing(projectId);
      window.location.reload();
    } catch (e) {
      setRerunError(e?.response?.data?.detail ?? "Erreur lors du relancement.");
      setRerunning(false);
    }
  };

  const errorStep = Object.entries(steps).find(([, s]) => s?.status === "error");
  const errorMsg  = errorStep ? errorStep[1]?.error : null;

  // ── Stepper horizontal ────────────────────────────────────────
  const StepperBar = () => (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      <div className="flex">
        {SUB_STEPS.map((step, idx) => {
          const StepIcon = step.icon;
          const status   = steps[step.key]?.status ?? "pending";
          const isActive = activeStep === step.key;
          const clickable = status === "done" || status === "error";

          return (
            <button
              key={step.key}
              type="button"
              disabled={!clickable}
              onClick={() => clickable && setActiveStep(step.key)}
              className={clsx(
                "flex-1 flex flex-col items-center gap-1.5 px-3 py-4 text-center transition-colors relative",
                "border-r border-slate-100 last:border-r-0",
                clickable ? "cursor-pointer" : "cursor-default",
                isActive
                  ? "bg-navy/5"
                  : clickable
                  ? "hover:bg-slate-50"
                  : "",
              )}
            >
              {/* Indicateur actif — barre en bas */}
              {isActive && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-navy rounded-t" />
              )}

              {/* Bulle numéro / icône statut */}
              <div className={clsx(
                "w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0",
                status === "done"    && "bg-green-500 text-white",
                status === "running" && "bg-blue-500  text-white animate-pulse",
                status === "error"   && "bg-red-500   text-white",
                status === "pending" && "bg-slate-100 text-slate-400",
              )}>
                {status === "done"
                  ? <CheckCircle size={13} />
                  : status === "running"
                  ? <Loader size={13} className="animate-spin" />
                  : status === "error"
                  ? <AlertCircle size={13} />
                  : <span>{idx + 1}</span>
                }
              </div>

              {/* Icône métier */}
              <StepIcon size={13} className={clsx(
                "shrink-0",
                status === "done"    && "text-green-500",
                status === "running" && "text-blue-500",
                status === "error"   && "text-red-500",
                status === "pending" && "text-slate-300",
              )} />

              {/* Label */}
              <p className={clsx(
                "text-[11px] font-medium leading-tight",
                isActive             && "text-navy",
                !isActive && status === "done"    && "text-slate-700",
                !isActive && status === "running" && "text-blue-600",
                !isActive && status === "error"   && "text-red-600",
                !isActive && status === "pending" && "text-slate-400",
              )}>
                {step.label}
              </p>

              {/* Badge statut compact */}
              <StepStatusBadge status={status} />
            </button>
          );
        })}
      </div>
    </div>
  );

  // ── Panneau de contenu du step actif ─────────────────────────
  const ActiveContent = () => {
    if (!activeStep) {
      return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 py-12 text-center">
          <p className="text-sm text-slate-400 italic">
            Aucune sous-étape terminée pour l&apos;instant.
          </p>
        </div>
      );
    }

    const stepMeta = SUB_STEPS.find((s) => s.key === activeStep);
    const stepData = steps[activeStep] ?? {};
    const status   = stepData.status ?? "pending";

    return (
      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        {/* Header du panneau */}
        <div className="flex items-center gap-2 px-5 py-3.5 border-b border-slate-100 bg-slate-50">
          {stepMeta && <stepMeta.icon size={14} className="text-navy shrink-0" />}
          <p className="text-sm font-semibold text-navy flex-1">{stepMeta?.label}</p>
          <StepStatusBadge status={status} />
        </div>

        {/* Contenu */}
        <div className="p-5">
          {status === "error" && (
            <div className="space-y-3">
              <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                <AlertCircle size={15} className="text-red-500 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-red-700">Erreur lors de cette étape</p>
                  <p className="text-xs text-red-600 mt-1 break-words">{stepData.error}</p>
                </div>
              </div>
              {rerunError && (
                <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 border border-red-200">
                  {rerunError}
                </p>
              )}
              <button
                onClick={handleRerun}
                disabled={rerunning}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-medium hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                <RefreshCw size={12} className={rerunning ? "animate-spin" : ""} />
                {rerunning ? "Relancement…" : "Relancer le staffing"}
              </button>
            </div>
          )}

          {status === "pending" && (
            <p className="text-sm text-slate-400 italic text-center py-8">
              Cette étape n&apos;a pas encore démarré.
            </p>
          )}

          {status === "running" && (
            <div className="flex items-center justify-center gap-2 py-8 text-blue-600">
              <Loader size={16} className="animate-spin" />
              <p className="text-sm font-medium">Traitement en cours…</p>
            </div>
          )}

          {status === "done" && activeStep === "profile_extraction" && (
            <ProfileExtractionResult
              result={stepData.result}
              storyMap={storyMap}
              loading={loading}
              projectId={projectId}
            />
          )}

          {status === "done" && activeStep === "profile_normalization" && (
            <div className="space-y-4">
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5">
                <p className="text-xs text-amber-700 font-medium">
                  Vérifiez les correspondances et ajustez les décisions si nécessaire.
                  Les profils marqués <strong>À Recruter</strong> seront exclus de la recherche en base.
                </p>
              </div>
              <ProfileNormalizationResult
                result={stepData.result}
                projectId={projectId}
              />
            </div>
          )}

          {status === "done" && activeStep === "story_distribution" && (
            <StoryDistributionResult
              result={stepData.result}
              projectId={projectId}
              project={project}
              onApplied={onRefresh}
            />
          )}

          {status === "done" && activeStep === "candidate_filtering" && (
            <CandidateFilteringResult result={stepData.result} />
          )}

          {status === "done" && activeStep === "matching" && (
            <MatchingResultCard
              result={stepData.result}
              projectId={projectId}
              project={project}
              currentUserName={aiOutput?.user_name ?? aiOutput?.pm_name ?? null}
              onRefresh={onRefresh}
            />
          )}

          {status === "done" && activeStep === "velocity_feasibility" && (
            <p className="text-sm text-slate-400 italic text-center py-8">
              Résultat vélocité & faisabilité disponible — affichage à venir.
            </p>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <ProjectDurationBanner
        startDate={project?.start_date}
        endDate={project?.end_date}
      />
      <StepperBar />
      <ActiveContent />
    </div>
  );
}
