import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Folder, Plus, Search, AlertCircle, Archive, Trash2, X, Code2, PackageCheck } from "lucide-react";
import clsx from "clsx";
import {
  getPipelineProjects,
  getArchivedProjects,
  archiveProject,
  unarchiveProject,
  deleteProject,
  advanceProjectStatus,
} from "../../api/pipeline";
import ProjectCard from "./components/ProjectCard";
import SkeletonCard from "./components/SkeletonCard";

// ── Raisons d'archivage ───────────────────────────────────────
const ARCHIVE_REASONS = [
  { value: "completed",  label: "Projet terminé"  },
  { value: "cancelled",  label: "Projet annulé"   },
  { value: "on_hold",    label: "Projet suspendu" },
  { value: "other",      label: "Autre raison"    },
];

// ── Labels des raisons pour affichage en badge ───────────────
const REASON_LABELS = Object.fromEntries(ARCHIVE_REASONS.map((r) => [r.value, r.label]));

export default function MesProjets() {
  const nav = useNavigate();

  const [projects,         setProjects]         = useState([]);
  const [archivedProjects, setArchivedProjects]  = useState([]);
  const [loading,          setLoading]           = useState(true);
  const [error,            setError]             = useState(null);
  const [search,           setSearch]            = useState("");
  const [filter,           setFilter]            = useState("all");
  const [showArchived,     setShowArchived]       = useState(false);

  // ── Modals ────────────────────────────────────────────────
  const [archiveModal, setArchiveModal] = useState(null);   // project object
  const [archiveReason, setArchiveReason] = useState("completed");
  const [deleteModal,  setDeleteModal]  = useState(null);   // project object
  const [actionLoading, setActionLoading] = useState(false);

  // ── Chargement ────────────────────────────────────────────
  const loadActive = () =>
    getPipelineProjects()
      .then(setProjects)
      .catch(() => setError("Impossible de charger les projets."))
      .finally(() => setLoading(false));

  const loadArchived = () =>
    getArchivedProjects()
      .then(setArchivedProjects)
      .catch(() => {});

  useEffect(() => {
    loadActive();
    loadArchived();
  }, []);

  // ── Filtres ───────────────────────────────────────────────
  const counts = {
    all:            projects.length,
    pending_human:  projects.filter((p) => p.global_status === "pending_human").length,
    in_progress:    projects.filter((p) => p.global_status === "in_progress").length,
    pipeline_done:  projects.filter((p) => p.global_status === "pipeline_done").length,
    in_development: projects.filter((p) => p.global_status === "in_development").length,
    delivered:      projects.filter((p) => p.global_status === "delivered").length,
  };

  const filtered = projects.filter((p) => {
    const matchSearch = (p.project_name + p.client_name).toLowerCase().includes(search.toLowerCase());
    const matchFilter = filter === "all" || p.global_status === filter;
    return matchSearch && matchFilter;
  });

  const filteredArchived = archivedProjects.filter((p) =>
    (p.project_name + p.client_name).toLowerCase().includes(search.toLowerCase())
  );

  const FILTERS = [
    { key: "all",            label: `Tous (${counts.all})` },
    { key: "pending_human",  label: `En attente (${counts.pending_human})` },
    { key: "in_progress",    label: `Pipeline IA (${counts.in_progress})` },
    { key: "pipeline_done",  label: `Pipeline terminé (${counts.pipeline_done})` },
    { key: "in_development", label: `En développement (${counts.in_development})` },
    { key: "delivered",      label: `Livrés (${counts.delivered})` },
  ];

  // ── Actions ───────────────────────────────────────────────
  const handleUnarchive = async (project) => {
    try {
      await unarchiveProject(project.project_id);
      setArchivedProjects((prev) => prev.filter((p) => p.project_id !== project.project_id));
      setProjects((prev) => [{ ...project, archived: false, archive_reason: null }, ...prev]);
    } catch {
      setError("Erreur lors du désarchivage du projet.");
    }
  };

  const handleAdvanceStatus = async (project) => {
    try {
      const { status } = await advanceProjectStatus(project.project_id);
      setProjects((prev) =>
        prev.map((p) => p.project_id === project.project_id ? { ...p, global_status: status } : p)
      );
    } catch {
      setError("Erreur lors de la mise à jour du statut.");
    }
  };

  const handleArchiveConfirm = async () => {
    if (!archiveModal) return;
    setActionLoading(true);
    try {
      await archiveProject(archiveModal.project_id, archiveReason);
      setProjects((prev) => prev.filter((p) => p.project_id !== archiveModal.project_id));
      setArchivedProjects((prev) => [
        { ...archiveModal, archived: true, archive_reason: archiveReason },
        ...prev,
      ]);
      setArchiveModal(null);
    } catch {
      setError("Erreur lors de l'archivage du projet.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteModal) return;
    setActionLoading(true);
    try {
      await deleteProject(deleteModal.project_id);
      setProjects((prev) => prev.filter((p) => p.project_id !== deleteModal.project_id));
      setArchivedProjects((prev) => prev.filter((p) => p.project_id !== deleteModal.project_id));
      setDeleteModal(null);
    } catch {
      setError("Erreur lors de la suppression du projet.");
    } finally {
      setActionLoading(false);
    }
  };

  // ── Rendu ─────────────────────────────────────────────────
  const displayedList   = showArchived ? filteredArchived : filtered;
  const isEmptyArchived = showArchived && filteredArchived.length === 0;
  const isEmptyActive   = !showArchived && filtered.length === 0;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* En-tête */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display font-bold text-navy text-2xl">Mes Projets</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {loading ? "..." : `${counts.all} projet${counts.all > 1 ? "s" : ""} · pipeline IA`}
          </p>
        </div>
        <button onClick={() => nav("/nouveau-projet")} className="btn-primary flex items-center gap-2">
          <Plus size={16} /> Nouveau projet
        </button>
      </div>

      {/* Filtres + recherche */}
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un projet ou client..."
            className="w-full pl-9 pr-4 py-2.5 text-sm border border-slate-200 rounded-xl
                       focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan" />
        </div>
        {!showArchived && (
          <div className="flex gap-2 flex-wrap">
            {FILTERS.map((f) => (
              <button key={f.key} onClick={() => setFilter(f.key)}
                className={clsx(
                  "text-xs px-3 py-2 rounded-xl font-medium transition-all whitespace-nowrap",
                  filter === f.key ? "bg-navy text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200",
                )}>
                {f.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Toggle Archivés */}
      <div className="flex items-center gap-2 mb-5">
        <button
          onClick={() => { setShowArchived((v) => !v); setFilter("all"); }}
          className={clsx(
            "flex items-center gap-2 text-xs px-3 py-2 rounded-xl font-medium transition-all border",
            showArchived
              ? "bg-amber-50 border-amber-200 text-amber-700"
              : "bg-slate-100 border-slate-200 text-slate-500 hover:bg-slate-200",
          )}
        >
          <Archive size={13} />
          {showArchived
            ? `Archivés (${archivedProjects.length}) — retour aux actifs`
            : `Archivés (${archivedProjects.length})`}
        </button>
      </div>

      {/* Alerte validations en attente */}
      {!showArchived && counts.pending_human > 0 && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 mb-5 text-sm text-amber-700">
          <AlertCircle size={16} className="shrink-0" />
          <span><strong>{counts.pending_human} projet{counts.pending_human > 1 ? "s" : ""}</strong> en attente de votre validation.</span>
          <button onClick={() => setFilter("pending_human")} className="ml-auto text-xs underline underline-offset-2 hover:text-amber-900">
            Voir
          </button>
        </div>
      )}

      {/* Erreur API */}
      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl px-4 py-3 mb-5">
          <AlertCircle size={15} className="shrink-0" /> {error}
        </div>
      )}

      {/* Grille */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
        </div>
      ) : (isEmptyActive || isEmptyArchived) ? (
        <div className="text-center py-16 text-slate-400">
          <Folder size={36} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">
            {showArchived
              ? "Aucun projet archivé."
              : projects.length === 0
                ? "Aucun projet pour l'instant. Créez votre premier projet !"
                : "Aucun projet correspond à votre recherche."}
          </p>
          {!showArchived && projects.length === 0 && (
            <button onClick={() => nav("/nouveau-projet")} className="btn-primary mt-4 inline-flex items-center gap-2">
              <Plus size={15} /> Créer un projet
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {displayedList.map((project) => (
            <ProjectCard
              key={project.project_id}
              project={project}
              onClick={() => nav(`/projet/${project.project_id}`)}
              onAdvance={!showArchived ? handleAdvanceStatus : undefined}
              onUnarchive={showArchived ? handleUnarchive : undefined}
              onArchive={showArchived ? undefined : (p) => { setArchiveModal(p); setArchiveReason("completed"); }}
              onDelete={(p) => setDeleteModal(p)}
            />
          ))}
        </div>
      )}

      {/* ── Modal Archiver ─────────────────────────────────── */}
      {archiveModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-amber-100 rounded-xl flex items-center justify-center">
                  <Archive size={16} className="text-amber-600" />
                </div>
                <h2 className="font-display font-bold text-navy text-base">Archiver le projet</h2>
              </div>
              <button onClick={() => setArchiveModal(null)} className="text-slate-400 hover:text-slate-600">
                <X size={18} />
              </button>
            </div>

            <p className="text-sm text-slate-600 mb-4">
              <strong>{archiveModal.project_name}</strong> sera masqué de la vue principale et déplacé dans les archivés.
            </p>

            <label className="block text-xs font-medium text-slate-500 mb-2">Raison de l'archivage</label>
            <div className="grid grid-cols-2 gap-2 mb-6">
              {ARCHIVE_REASONS.map((r) => (
                <button key={r.value}
                  onClick={() => setArchiveReason(r.value)}
                  className={clsx(
                    "text-sm px-4 py-2.5 rounded-xl border font-medium transition-all text-left",
                    archiveReason === r.value
                      ? "bg-amber-50 border-amber-300 text-amber-700"
                      : "border-slate-200 text-slate-600 hover:border-slate-300",
                  )}
                >
                  {r.label}
                </button>
              ))}
            </div>

            <div className="flex gap-3">
              <button onClick={() => setArchiveModal(null)}
                className="flex-1 text-sm px-4 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50">
                Annuler
              </button>
              <button onClick={handleArchiveConfirm} disabled={actionLoading}
                className="flex-1 text-sm px-4 py-2.5 rounded-xl bg-amber-500 text-white font-medium
                           hover:bg-amber-600 disabled:opacity-60 flex items-center justify-center gap-2">
                <Archive size={14} />
                {actionLoading ? "Archivage..." : "Archiver"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal Supprimer ────────────────────────────────── */}
      {deleteModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-red-100 rounded-xl flex items-center justify-center">
                  <Trash2 size={16} className="text-red-500" />
                </div>
                <h2 className="font-display font-bold text-navy text-base">Supprimer le projet</h2>
              </div>
              <button onClick={() => setDeleteModal(null)} className="text-slate-400 hover:text-slate-600">
                <X size={18} />
              </button>
            </div>

            <p className="text-sm text-slate-600 mb-1">
              Vous êtes sur le point de supprimer définitivement
            </p>
            <p className="text-sm font-semibold text-navy mb-4">"{deleteModal.project_name}"</p>
            <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-xs text-red-600 mb-6">
              Cette action est irréversible. Toutes les données pipeline, épics, stories et sprints seront perdus.
            </div>

            <div className="flex gap-3">
              <button onClick={() => setDeleteModal(null)}
                className="flex-1 text-sm px-4 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50">
                Annuler
              </button>
              <button onClick={handleDeleteConfirm} disabled={actionLoading}
                className="flex-1 text-sm px-4 py-2.5 rounded-xl bg-red-500 text-white font-medium
                           hover:bg-red-600 disabled:opacity-60 flex items-center justify-center gap-2">
                <Trash2 size={14} />
                {actionLoading ? "Suppression..." : "Supprimer définitivement"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
