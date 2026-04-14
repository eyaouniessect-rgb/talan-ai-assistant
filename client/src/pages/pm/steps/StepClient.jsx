import { useState, useEffect } from "react";
import { Search, Plus, Building2, ChevronRight, Loader } from "lucide-react";
import { getClients, createClient } from "../../../api/crm";
import ErrorBanner from "../components/ErrorBanner";

export default function StepClient({ onNext }) {
  const [clients,     setClients]     = useState([]);
  const [search,      setSearch]      = useState("");
  const [newMode,     setNewMode]     = useState(false);
  const [newName,     setNewName]     = useState("");
  const [newIndustry, setNewIndustry] = useState("");
  const [newEmail,    setNewEmail]    = useState("");
  const [loading,     setLoading]     = useState(false);
  const [fetching,    setFetching]    = useState(true);
  const [error,       setError]       = useState(null);

  useEffect(() => {
    getClients()
      .then(setClients)
      .catch(() => setError("Impossible de charger les clients."))
      .finally(() => setFetching(false));
  }, []);

  const filtered = clients.filter((c) => c.name.toLowerCase().includes(search.toLowerCase()));

  const handleCreate = async () => {
    if (!newName.trim()) return setError("Le nom du client est obligatoire.");
    setLoading(true);
    setError(null);
    try {
      const client = await createClient({ name: newName.trim(), industry: newIndustry.trim() || null, contact_email: newEmail.trim() || null });
      onNext(client);
    } catch (e) {
      setError(e.response?.data?.detail || "Erreur lors de la création du client.");
    } finally {
      setLoading(false);
    }
  };

  if (fetching)
    return <div className="flex items-center justify-center py-20"><Loader size={22} className="animate-spin text-cyan" /></div>;

  return (
    <div className="card p-8 space-y-5">
      <div>
        <h2 className="font-display text-xl font-bold text-navy mb-1">Sélectionner un client</h2>
        <p className="text-slate-500 text-sm">Choisissez un client existant ou créez-en un nouveau.</p>
      </div>

      {!newMode ? (
        <>
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Rechercher un client..."
              className="w-full pl-9 pr-4 py-2.5 text-sm border border-slate-200 rounded-xl
                         focus:outline-none focus:ring-2 focus:ring-cyan/30 focus:border-cyan"
            />
          </div>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {filtered.length === 0 && <p className="text-sm text-slate-400 text-center py-6">Aucun client trouvé.</p>}
            {filtered.map((c) => (
              <button key={c.id} onClick={() => onNext(c)}
                className="w-full flex items-center gap-3 p-3.5 rounded-xl border border-slate-200
                           hover:border-cyan/40 hover:bg-cyan/5 transition-all text-left group">
                <div className="w-9 h-9 bg-navy/5 rounded-xl flex items-center justify-center shrink-0 group-hover:bg-cyan/10 transition-colors">
                  <Building2 size={16} className="text-navy/60 group-hover:text-cyan transition-colors" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-navy truncate">{c.name}</div>
                  {c.industry && <div className="text-xs text-slate-400">{c.industry}</div>}
                </div>
                <ChevronRight size={14} className="text-slate-300 group-hover:text-cyan transition-colors shrink-0" />
              </button>
            ))}
          </div>

          <ErrorBanner msg={error} />

          <button onClick={() => { setNewMode(true); setError(null); }}
            className="btn-secondary w-full flex items-center justify-center gap-2">
            <Plus size={15} /> Nouveau client
          </button>
        </>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="text-xs font-semibold text-slate-600 mb-1 block">Nom du client <span className="text-red-500">*</span></label>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="ex: Talan Tunisie" className="input w-full" />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-600 mb-1 block">Secteur</label>
            <input value={newIndustry} onChange={(e) => setNewIndustry(e.target.value)} placeholder="ex: Finance, Energie, Santé..." className="input w-full" />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-600 mb-1 block">Email de contact</label>
            <input type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} placeholder="contact@client.com" className="input w-full" />
          </div>

          <ErrorBanner msg={error} />

          <div className="flex gap-3 pt-1">
            <button onClick={() => { setNewMode(false); setError(null); }} className="btn-secondary flex-1">Annuler</button>
            <button onClick={handleCreate} disabled={loading || !newName.trim()}
              className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
              {loading ? <Loader size={15} className="animate-spin" /> : <Plus size={15} />}
              Créer le client
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
