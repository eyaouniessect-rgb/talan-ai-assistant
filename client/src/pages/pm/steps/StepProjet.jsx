import { useState, useEffect } from "react";
import { FolderPlus, ChevronRight, Loader } from "lucide-react";
import { getCrmProjects, createProject } from "../../../api/crm";
import ErrorBanner from "../components/ErrorBanner";

export default function StepProjet({ selectedClient, onNext, onBack }) {
  const [name, setName] = useState("");
  const [existing, setExisting] = useState([]);
  const [fetching, setFetching] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setFetching(true);
    setError(null);
    getCrmProjects(selectedClient.id)
      .then(setExisting)
      .catch((e) => {
        const detail = e.response?.data?.detail;
        setError(
          typeof detail === "string"
            ? detail
            : "Impossible de récupérer les projets existants pour ce client.",
        );
      })
      .finally(() => setFetching(false));
  }, [selectedClient.id]);


  const handleCreate = async () => {
    if (!name.trim()) return setError("Le nom du projet est obligatoire.");
    setLoading(true);
    setError(null);
    try {
      const project = await createProject({
        name: name.trim(),
        client_id: selectedClient.id,
      });
      onNext(project);
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (e.response?.status === 409 && detail?.project_id) {
        onNext({ id: detail.project_id, name: detail.project_name });
      } else {
        setError(
          typeof detail === "string"
            ? detail
            : detail?.detail || "Erreur lors de la création du projet.",
        );
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card p-8 space-y-5">
      <div>
        <h2 className="font-display text-xl font-bold text-navy mb-1">
          Projet
        </h2>
        <p className="text-slate-500 text-sm">
          Client : <strong className="text-navy">{selectedClient?.name}</strong>
        </p>
      </div>

      {!fetching && existing.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Projets existants — continuer sur un projet existant
          </p>
          <div className="space-y-2 max-h-44 overflow-y-auto">
            {existing.map((p) => (
              <button
                key={p.id}
                onClick={() => onNext(p)}
                className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-200
                           hover:border-cyan/40 hover:bg-cyan/5 transition-all text-left group"
              >
                <div className="w-8 h-8 bg-navy/5 rounded-lg flex items-center justify-center shrink-0 group-hover:bg-cyan/10 transition-colors">
                  <FolderPlus
                    size={14}
                    className="text-navy/60 group-hover:text-cyan"
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-navy truncate">
                    {p.name}
                  </div>
                  <div className="text-xs text-slate-400">{p.status}</div>
                </div>
                <ChevronRight
                  size={13}
                  className="text-slate-300 group-hover:text-cyan shrink-0"
                />
              </button>
            ))}
          </div>
          <div className="flex items-center gap-3 my-3">
            <div className="flex-1 h-px bg-slate-200" />
            <span className="text-xs text-slate-400">ou créer un nouveau</span>
            <div className="flex-1 h-px bg-slate-200" />
          </div>
        </div>
      )}

      <div>
        <label className="text-xs font-semibold text-slate-600 mb-1 block">
          Nom du nouveau projet <span className="text-red-500">*</span>
        </label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          placeholder="ex: Plateforme e-commerce"
          className="input w-full text-base"
          autoFocus
        />
      </div>

      <ErrorBanner msg={error} />

      <div className="flex gap-3">
        <button onClick={onBack} className="btn-secondary flex-1">
          Retour
        </button>
        <button
          onClick={handleCreate}
          disabled={loading || !name.trim()}
          className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <Loader size={15} className="animate-spin" />
          ) : (
            <FolderPlus size={15} />
          )}
          Créer le projet
        </button>
      </div>
    </div>
  );
}
