import { useState, useEffect } from "react";
import { Rocket, Loader, ExternalLink, AlertCircle } from "lucide-react";
import clsx from "clsx";
import { useNavigate } from "react-router-dom";
import { startPipeline, getJiraConfig } from "../../../api/pipeline";
import ErrorBanner from "../components/ErrorBanner";

export default function StepLancement({ selectedClient, createdProject, uploadedDoc, onBack }) {
  const [jiraKey,     setJiraKey]     = useState("");
  const [jiraEnabled, setJiraEnabled] = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(null);
  const nav = useNavigate();

  // Savoir si Jira est configuré côté backend
  useEffect(() => {
    getJiraConfig()
      .then(({ jira_enabled }) => setJiraEnabled(jira_enabled))
      .catch(() => setJiraEnabled(false));
  }, []);

  const jiraKeyTrimmed = jiraKey.trim();
  const jiraKeyInvalid = jiraEnabled && !jiraKeyTrimmed;

  const handleStart = async () => {
    if (jiraKeyInvalid) return;
    setLoading(true);
    setError(null);
    try {
      await startPipeline(createdProject.id, {
        document_id:      uploadedDoc.document_id,
        jira_project_key: jiraKeyTrimmed,
      });
      nav(`/projet/${createdProject.id}`);
    } catch (e) {
      setError(e.response?.data?.detail || "Erreur lors du lancement du pipeline.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card p-8 space-y-5">
      <div>
        <h2 className="font-display text-xl font-bold text-navy mb-1">Lancer le pipeline IA</h2>
        <p className="text-slate-500 text-sm">Vérifiez les informations avant de démarrer l'analyse.</p>
      </div>

      {/* Récapitulatif */}
      <div className="bg-slate-50 rounded-2xl p-5 space-y-3">
        {[
          { label: "Client",  value: selectedClient?.name },
          { label: "Projet",  value: createdProject?.name },
          { label: "Fichier", value: uploadedDoc?.file_name },
        ].map(({ label, value }) => (
          <div key={label} className="flex justify-between text-sm">
            <span className="text-slate-500">{label}</span>
            <span className="font-semibold text-navy">{value}</span>
          </div>
        ))}
      </div>

      {/* Champ Jira — obligatoire si Jira activé, caché sinon */}
      {jiraEnabled ? (
        <div>
          <label className="text-xs font-semibold text-slate-600 mb-1 flex items-center gap-1.5">
            Clé du projet Jira
            <span className="text-red-500">*</span>
          </label>
          <input
            value={jiraKey}
            onChange={(e) => setJiraKey(e.target.value)}
            placeholder="ex: TALAN"
            className={clsx(
              "input w-full",
              jiraKeyInvalid && "border-red-300 focus:ring-red-200 focus:border-red-400",
            )}
          />
          {jiraKeyInvalid ? (
            <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
              <AlertCircle size={11} /> La clé Jira est obligatoire pour lancer le pipeline.
            </p>
          ) : (
            <p className="text-xs text-slate-400 mt-1 flex items-center gap-1">
              <ExternalLink size={11} />
              Clé du projet Jira existant (ex&nbsp;: TALAN). Les résultats seront synchronisés après chaque phase.
            </p>
          )}
        </div>
      ) : null}

      <ErrorBanner msg={error} />

      <div className="flex gap-3">
        <button onClick={onBack} disabled={loading} className="btn-secondary flex-1">
          Retour
        </button>
        <button
          onClick={handleStart}
          disabled={loading || jiraKeyInvalid}
          className={clsx(
            "btn-primary flex-1 flex items-center justify-center gap-2",
            (loading || jiraKeyInvalid) && "opacity-75 cursor-not-allowed",
          )}
        >
          {loading
            ? <><Loader size={15} className="animate-spin" /> Lancement...</>
            : <><Rocket size={15} /> Lancer l'analyse IA</>}
        </button>
      </div>
    </div>
  );
}
