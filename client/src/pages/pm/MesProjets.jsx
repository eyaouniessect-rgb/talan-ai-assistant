import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Folder, Plus, Search, AlertCircle } from "lucide-react";
import clsx from "clsx";
import { getPipelineProjects } from "../../api/pipeline";
import ProjectCard from "./components/ProjectCard";
import SkeletonCard from "./components/SkeletonCard";

export default function MesProjets() {
  const nav = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [search,   setSearch]   = useState("");
  const [filter,   setFilter]   = useState("all");

  useEffect(() => {
    getPipelineProjects()
      .then(setProjects)
      .catch(() => setError("Impossible de charger les projets."))
      .finally(() => setLoading(false));
  }, []);

  const counts = {
    all:           projects.length,
    pending_human: projects.filter((p) => p.global_status === "pending_human").length,
    in_progress:   projects.filter((p) => p.global_status === "in_progress").length,
    completed:     projects.filter((p) => p.global_status === "completed").length,
  };

  const filtered = projects.filter((p) => {
    const matchSearch = (p.project_name + p.client_name).toLowerCase().includes(search.toLowerCase());
    const matchFilter = filter === "all" || p.global_status === filter;
    return matchSearch && matchFilter;
  });

  const FILTERS = [
    { key: "all",           label: `Tous (${counts.all})` },
    { key: "pending_human", label: `En attente (${counts.pending_human})` },
    { key: "in_progress",   label: `En cours (${counts.in_progress})` },
    { key: "completed",     label: `Terminés (${counts.completed})` },
  ];

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
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un projet ou client..."
            className="w-full pl-9 pr-4 py-2.5 text-sm border border-slate-200 rounded-xl
                       focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan" />
        </div>
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
      </div>

      {/* Alerte validations en attente */}
      {counts.pending_human > 0 && (
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
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <Folder size={36} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">
            {projects.length === 0 ? "Aucun projet pour l'instant. Créez votre premier projet !" : "Aucun projet correspond à votre recherche."}
          </p>
          {projects.length === 0 && (
            <button onClick={() => nav("/nouveau-projet")} className="btn-primary mt-4 inline-flex items-center gap-2">
              <Plus size={15} /> Créer un projet
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((project) => (
            <ProjectCard key={project.project_id} project={project} onClick={() => nav(`/projet/${project.project_id}`)} />
          ))}
        </div>
      )}
    </div>
  );
}
