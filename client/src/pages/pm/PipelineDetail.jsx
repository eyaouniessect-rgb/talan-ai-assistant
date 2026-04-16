import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  CheckCircle,
  Loader,
  ChevronLeft,
  AlertCircle,
  Rocket,
  Tag,
  RefreshCw,
} from "lucide-react";
import clsx from "clsx";
import {
  getPipelineDetail,
  validatePhase,
  startPipeline,
  resyncJira,
} from "../../api/pipeline";
import { getDocument } from "../../api/projects";
import { PHASES, PHASE_KEY_MAP } from "./constants/phases";
import PhaseList from "./components/PhaseList";
import PhaseResult from "./components/PhaseResult";
import ValidationCard from "./components/ValidationCard";
import ProcessingCard from "./components/ProcessingCard";
import StoriesStreamCard from "./components/StoriesStreamCard";

export default function PipelineDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const pollRef = useRef(null);

  const [project, setProject] = useState(null);
  const [phaseMap, setPhaseMap] = useState({});
  const [activePhase, setActivePhase] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [existingDoc, setExistingDoc] = useState(null);
  const [docLoading, setDocLoading] = useState(false);
  const [startLoading, setStartLoading] = useState(false);
  const [startError, setStartError] = useState(null);
  const [jiraKey, setJiraKey] = useState("");
  const [processingState, setProcessingState] = useState(null); // { phase, approved }
  const [resyncLoading, setResyncLoading] = useState(false);
  const [resyncResult, setResyncResult] = useState(null); // { ok, message }

  const fetchData = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      try {
        const data = await getPipelineDetail(id);
        setProject(data);

        const map = {};
        for (const phase of data.phases) {
          const key = PHASE_KEY_MAP[phase.phase] ?? phase.phase;
          map[key] = phase;
        }
        setPhaseMap(map);

        const pending = data.phases.find(
          (p) => p.status === "pending_validation",
        );
        if (pending) {
          setActivePhase(PHASE_KEY_MAP[pending.phase] ?? pending.phase);
        } else {
          setActivePhase((prev) => {
            if (prev) return prev;
            const last = data.phases[data.phases.length - 1];
            return last ? (PHASE_KEY_MAP[last.phase] ?? last.phase) : null;
          });
        }
        setError(null);
      } catch {
        setError("Impossible de charger les données du pipeline.");
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [id],
  ); // eslint-disable-line

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!project) return;
    const hasRunning = project.phases.some(
      (p) => p.status === "pending_ai" || p.status === "in_progress",
    );
    if (hasRunning) {
      pollRef.current = setInterval(() => fetchData(true), 4000);
    } else {
      clearInterval(pollRef.current);
    }
    return () => clearInterval(pollRef.current);
  }, [project, fetchData]);

  useEffect(() => {
    if (!project || project.phases.length !== 0) {
      setExistingDoc(null);
      setStartError(null);
      return;
    }

    let cancelled = false;
    setDocLoading(true);
    getDocument(id)
      .then((doc) => {
        if (cancelled) return;
        setExistingDoc(doc);
        setStartError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        if (e.response?.status === 404) {
          setExistingDoc(null);
          setStartError(null);
          return;
        }
        setExistingDoc(null);
        setStartError("Impossible de vérifier le CDC de ce projet.");
      })
      .finally(() => {
        if (!cancelled) setDocLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id, project]);

  const handleStartPipeline = async () => {
    if (!existingDoc?.document_id) {
      setStartError(
        "Aucun CDC trouvé. Retournez au parcours Nouveau Projet pour uploader le document.",
      );
      return;
    }

    setStartLoading(true);
    setStartError(null);
    try {
      await startPipeline(id, {
        document_id: existingDoc.document_id,
        jira_project_key: jiraKey.trim() || "",
      });
      await fetchData();
    } catch (e) {
      setStartError(
        e.response?.data?.detail || "Erreur lors du lancement du pipeline.",
      );
    } finally {
      setStartLoading(false);
    }
  };

  const handleResyncJira = async (phaseKey) => {
    setResyncLoading(true);
    setResyncResult(null);
    try {
      const res = await resyncJira(id, phaseKey);
      setResyncResult({ ok: true, message: res.message });
    } catch (e) {
      setResyncResult({
        ok: false,
        message: e.response?.data?.detail || "Erreur lors de la re-sync Jira.",
      });
    } finally {
      setResyncLoading(false);
    }
  };

  const getPhaseStatus = (key) => {
    const phase = phaseMap[key];
    if (!phase) return "pending";
    if (phase.status === "validated") return "done";
    if (phase.status === "pending_validation") return "active";
    if (phase.status === "pending_ai") return "running";
    if (phase.status === "rejected") return "rejected";
    return "pending";
  };

  const globalStatus = (() => {
    if (!project || project.phases.length === 0) return "not_started";
    if (
      project.phases.every((p) => p.status === "validated") &&
      project.phases.length === 12
    )
      return "completed";
    if (project.phases.some((p) => p.status === "pending_validation"))
      return "pending_human";
    if (project.phases.some((p) => p.status === "pending_ai")) return "running";
    return "in_progress";
  })();

  if (loading)
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <div className="h-5 w-32 bg-slate-100 rounded animate-pulse mb-6" />
        <div className="h-8 w-64 bg-slate-100 rounded animate-pulse mb-2" />
        <div className="h-4 w-48 bg-slate-100 rounded animate-pulse mb-8" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="card p-4 animate-pulse h-96" />
          <div className="lg:col-span-2 card p-5 animate-pulse h-96" />
        </div>
      </div>
    );

  if (error)
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <button
          onClick={() => nav("/mes-projets")}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-navy mb-5"
        >
          <ChevronLeft size={16} /> Mes projets
        </button>
        <div className="flex items-center gap-3 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3">
          <AlertCircle size={16} className="shrink-0" /> {error}
        </div>
      </div>
    );

  const activePhaseData = PHASES.find((p) => p.id === activePhase);
  const activePhaseDb = phaseMap[activePhase];
  const isPendingHuman =
    activePhase && phaseMap[activePhase]?.status === "pending_validation";

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <button
        onClick={() => nav("/mes-projets")}
        className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-navy mb-5 transition-colors"
      >
        <ChevronLeft size={16} /> Mes projets
      </button>

      {/* En-tête */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="font-display font-bold text-navy text-2xl">
            {project?.project_name}
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Pipeline IA · {project?.phases.length ?? 0} / 12 phases enregistrées
          </p>
          {project?.jira_project_key && (
            <span className="inline-flex items-center gap-1 mt-1 text-xs text-indigo-600 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full">
              <Tag size={10} /> Jira : {project.jira_project_key}
            </span>
          )}
        </div>
        {globalStatus === "pending_human" && (
          <span className="text-xs bg-amber-50 text-amber-600 border border-amber-200 px-3 py-1.5 rounded-full font-medium flex items-center gap-1.5">
            <AlertCircle size={12} /> Validation requise
          </span>
        )}
        {globalStatus === "running" && (
          <span className="text-xs bg-blue-50 text-blue-600 border border-blue-200 px-3 py-1.5 rounded-full font-medium flex items-center gap-1.5">
            <Loader size={12} className="animate-spin" /> En cours...
          </span>
        )}
        {globalStatus === "completed" && (
          <span className="text-xs bg-green-50 text-green-600 border border-green-200 px-3 py-1.5 rounded-full font-medium flex items-center gap-1.5">
            <CheckCircle size={12} /> Terminé
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Colonne gauche : liste des phases */}
        <div className="lg:col-span-1">
          <PhaseList
            activePhase={activePhase}
            getPhaseStatus={getPhaseStatus}
            onSelect={setActivePhase}
          />
        </div>

        {/* Colonne droite : résultat IA + validation */}
        <div className="lg:col-span-2 space-y-4">
          {project?.phases.length === 0 && (
            <div className="card p-6 space-y-4">
              <div className="text-center text-slate-500">
                <Loader size={28} className="mx-auto mb-3 opacity-30" />
                <p className="text-sm">
                  Le pipeline n'a pas encore démarré pour ce projet.
                </p>
              </div>

              <div className="bg-slate-50 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-500">CDC</span>
                  <span className="font-medium text-navy">
                    {docLoading
                      ? "Vérification..."
                      : existingDoc?.file_name || "Aucun CDC trouvé"}
                  </span>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-600 mb-1 block">
                    Clé Jira{" "}
                    <span className="text-slate-400 font-normal">
                      (optionnel)
                    </span>
                  </label>
                  <input
                    value={jiraKey}
                    onChange={(e) => setJiraKey(e.target.value)}
                    placeholder="ex: TALAN-2024"
                    className="input w-full"
                  />
                </div>

                {startError && (
                  <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-3 py-2 text-xs">
                    <AlertCircle size={14} className="shrink-0" />
                    <span>{startError}</span>
                  </div>
                )}

                <button
                  onClick={handleStartPipeline}
                  disabled={
                    startLoading || docLoading || !existingDoc?.document_id
                  }
                  className={clsx(
                    "btn-primary w-full flex items-center justify-center gap-2",
                    (startLoading || docLoading || !existingDoc?.document_id) &&
                      "opacity-60 cursor-not-allowed",
                  )}
                >
                  {startLoading ? (
                    <>
                      <Loader size={15} className="animate-spin" /> Lancement...
                    </>
                  ) : (
                    <>
                      <Rocket size={15} /> Démarrer le pipeline
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {activePhaseData && (
            <div className="card p-5">
              <div className="flex items-start justify-between mb-1">
                <div className="flex items-center gap-2">
                  <activePhaseData.icon size={18} className="text-cyan" />
                  <h2 className="font-display font-bold text-navy text-base">
                    {activePhaseData.label}
                  </h2>
                </div>
                <div className="flex items-center gap-2">
                  {getPhaseStatus(activePhase) === "done" && (
                    <span className="flex items-center gap-1 text-xs text-green-600 bg-green-50 px-2.5 py-1 rounded-full">
                      <CheckCircle size={11} /> Validé
                    </span>
                  )}
                  {getPhaseStatus(activePhase) === "done" &&
                    project?.jira_project_key &&
                    ["epics", "stories", "tasks", "sprints"].includes(activePhase) && (
                      <button
                        onClick={() => handleResyncJira(activePhase)}
                        disabled={resyncLoading}
                        title="Forcer la re-synchronisation vers Jira"
                        className="flex items-center gap-1 text-xs text-indigo-600 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 px-2.5 py-1 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <RefreshCw size={11} className={resyncLoading ? "animate-spin" : ""} />
                        {resyncLoading ? "Sync..." : "Re-sync Jira"}
                      </button>
                    )}
                </div>
                {getPhaseStatus(activePhase) === "active" && (
                  <span className="flex items-center gap-1 text-xs text-amber-600 bg-amber-50 px-2.5 py-1 rounded-full">
                    <AlertCircle size={11} /> En attente
                  </span>
                )}
                {getPhaseStatus(activePhase) === "running" && (
                  <span className="flex items-center gap-1 text-xs text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full">
                    <Loader size={11} className="animate-spin" /> En cours...
                  </span>
                )}
                {getPhaseStatus(activePhase) === "rejected" && (
                  <span className="flex items-center gap-1 text-xs text-red-600 bg-red-50 px-2.5 py-1 rounded-full">
                    <AlertCircle size={11} /> Rejeté
                  </span>
                )}
              </div>

              <p className="text-xs text-slate-400 mb-4">
                {activePhaseData.desc}
              </p>

              {getPhaseStatus(activePhase) === "running" ? (
                activePhase === "stories" ? (
                  <StoriesStreamCard projectId={parseInt(id)} />
                ) : (
                  <div className="flex items-center gap-3 text-blue-600 text-sm py-4">
                    <Loader size={18} className="animate-spin shrink-0" /> L'IA
                    traite cette phase...
                  </div>
                )
              ) : (
                <PhaseResult
                  phaseId={activePhase}
                  aiOutput={activePhaseDb?.ai_output}
                />
              )}

              {activePhaseDb?.updated_at && (
                <p className="text-xs text-slate-400 mt-4">
                  Mis à jour :{" "}
                  {new Date(activePhaseDb.updated_at).toLocaleString("fr-FR")}
                </p>
              )}
            </div>
          )}

          {resyncResult && (
            <div
              className={clsx(
                "card p-3 flex items-center justify-between gap-3 text-sm",
                resyncResult.ok
                  ? "border border-green-200 bg-green-50 text-green-800"
                  : "border border-red-200 bg-red-50 text-red-800",
              )}
            >
              <div className="flex items-center gap-2">
                {resyncResult.ok ? (
                  <CheckCircle size={15} className="shrink-0 text-green-500" />
                ) : (
                  <AlertCircle size={15} className="shrink-0 text-red-500" />
                )}
                <span>{resyncResult.message}</span>
              </div>
              <button
                onClick={() => setResyncResult(null)}
                className="text-xs opacity-60 hover:opacity-100"
              >
                ✕
              </button>
            </div>
          )}

          {processingState ? (
            <ProcessingCard
              currentPhase={processingState.phase}
              approved={processingState.approved}
            />
          ) : isPendingHuman ? (
            <ValidationCard
              onValidate={async (approved, feedback) => {
                setProcessingState({ phase: activePhase, approved });
                try {
                  await validatePhase(id, { approved, feedback });
                  await fetchData();
                } finally {
                  setProcessingState(null);
                }
              }}
            />
          ) : null}

          {globalStatus === "completed" && (
            <div className="card p-4 border border-green-200 bg-green-50 flex items-center gap-3">
              <CheckCircle size={20} className="text-green-500 shrink-0" />
              <div>
                <p className="text-sm font-medium text-green-800">
                  Pipeline terminé
                </p>
                <p className="text-xs text-green-600">
                  Toutes les phases ont été validées.
                </p>
              </div>
            </div>
          )}

          {globalStatus === "running" && !activePhaseDb && (
            <div className="card p-4 border border-blue-200 bg-blue-50 flex items-center gap-3">
              <Loader
                size={20}
                className="text-blue-500 animate-spin shrink-0"
              />
              <div>
                <p className="text-sm font-medium text-blue-800">
                  Pipeline en cours
                </p>
                <p className="text-xs text-blue-600">
                  Rafraîchissement automatique toutes les 4 secondes.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
