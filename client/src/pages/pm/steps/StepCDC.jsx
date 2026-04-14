import { useState, useEffect } from "react";
import { Upload, CheckCircle, Loader } from "lucide-react";
import clsx from "clsx";
import { uploadDocument, getDocument } from "../../../api/projects";
import ErrorBanner from "../components/ErrorBanner";

export default function StepCDC({ createdProject, onNext, onBack }) {
  const [file,        setFile]        = useState(null);
  const [existingDoc, setExistingDoc] = useState(null); // CDC déjà uploadé pour ce projet
  const [dragging,    setDragging]    = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(null);

  // Charger le document existant si le projet en a déjà un
  useEffect(() => {
    getDocument(createdProject.id)
      .then(setExistingDoc)
      .catch(() => {}); // 404 = aucun document, c'est normal
  }, []);

  const handleFile = (f) => {
    if (!f) return;
    const ext = f.name.split(".").pop().toLowerCase();
    if (!["pdf", "docx", "txt"].includes(ext)) return setError("Format non supporté. Envoyez un PDF, DOCX ou TXT.");
    if (f.size > 10 * 1024 * 1024) return setError("Fichier trop volumineux. Maximum 10 MB.");
    setError(null);
    setFile(f);
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const doc = await uploadDocument(createdProject.id, file);
      onNext(doc);
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (e.response?.status === 409 && detail?.document_id) {
        onNext({ document_id: detail.document_id, file_name: detail.file_name });
      } else {
        setError(typeof detail === "string" ? detail : "Erreur lors de l'upload.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card p-8 space-y-5">
      <div>
        <h2 className="font-display text-xl font-bold text-navy mb-1">Cahier des charges</h2>
        <p className="text-slate-500 text-sm">
          Projet : <strong className="text-navy">{createdProject?.name}</strong>
        </p>
      </div>

      {/* Document déjà présent — option de réutiliser ou remplacer */}
      {existingDoc && !file && (
        <div className="flex items-start gap-3 bg-blue-50 border border-blue-200 rounded-xl px-4 py-3">
          <CheckCircle size={16} className="text-blue-500 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-blue-800">CDC déjà uploadé</p>
            <p className="text-xs text-blue-600 truncate">{existingDoc.file_name}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => onNext({ document_id: existingDoc.document_id, file_name: existingDoc.file_name })}
              className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700 transition-colors"
            >
              Utiliser
            </button>
            <button
              onClick={() => setExistingDoc(null)}
              className="text-xs text-blue-500 underline hover:text-blue-700"
            >
              Remplacer
            </button>
          </div>
        </div>
      )}

      {/* Zone de drop — masquée si on a un doc existant non ignoré */}
      {!existingDoc && (
        <>
          <div
            onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onClick={() => !file && document.getElementById("cdc-file-input").click()}
            className={clsx(
              "border-2 border-dashed rounded-2xl p-12 text-center transition-all cursor-pointer",
              dragging ? "border-cyan bg-cyan/5" : file ? "border-green-400 bg-green-50" : "border-slate-200 hover:border-slate-300",
            )}
          >
            {file ? (
              <>
                <CheckCircle size={36} className="text-green-500 mx-auto mb-3" />
                <p className="font-semibold text-green-700">{file.name}</p>
                <p className="text-xs text-green-500 mt-1">{(file.size / 1024).toFixed(0)} KB</p>
                <button onClick={(e) => { e.stopPropagation(); setFile(null); setError(null); }}
                  className="text-xs text-slate-400 underline mt-2 hover:text-red-500">
                  Changer de fichier
                </button>
              </>
            ) : (
              <>
                <Upload size={36} className="text-slate-300 mx-auto mb-3" />
                <p className="text-slate-600 font-medium">Déposez votre fichier ici</p>
                <p className="text-xs text-slate-400 mt-1 mb-4">PDF, DOCX, TXT · max 10 MB</p>
                <span className="btn-secondary text-sm">Parcourir</span>
              </>
            )}
          </div>
          <input id="cdc-file-input" type="file" accept=".pdf,.docx,.txt" className="hidden"
            onChange={(e) => handleFile(e.target.files[0])} />

          <ErrorBanner msg={error} />

          <div className="flex gap-3">
            <button onClick={onBack} className="btn-secondary flex-1">Retour</button>
            <button onClick={handleUpload} disabled={loading || !file}
              className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
              {loading ? <Loader size={15} className="animate-spin" /> : <Upload size={15} />}
              Uploader le CDC
            </button>
          </div>
        </>
      )}

      {/* Bouton retour visible même quand un doc existant est affiché */}
      {existingDoc && (
        <button onClick={onBack} className="btn-secondary w-full">Retour</button>
      )}
    </div>
  );
}
