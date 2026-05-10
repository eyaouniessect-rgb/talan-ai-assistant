// client/src/pages/pm/components/RecruitmentRequestDialog.jsx
// Modale "Signaler un besoin en recrutement" — UI type éditeur d'email.
// Le PM peut éditer To/CC/Sujet/Corps avant envoi à l'équipe RH.

import { useState, useMemo, useEffect, useRef } from "react";
import { X, Send, Loader, Mail, Users } from "lucide-react";
import clsx from "clsx";
import { sendRecruitmentRequest, getHrContacts } from "../../../api/pipeline";


const isValidEmail = (e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);


function buildDefaultSubject(profile, projectName) {
  return `Besoin en recrutement : ${profile} — ${projectName}`;
}


function buildDefaultBody({ profile, level, skills, projectName, sprintLabel, pmName }) {
  const skillsLine = skills?.length ? skills.join(", ") : "—";
  const lines = [
    "Bonjour,",
    "",
    `Dans le cadre du projet « ${projectName} », j'identifie un besoin de recrutement non couvert par les profils internes.`,
    "",
    "Détails du besoin :",
    `- Profil : ${profile}`,
    `- Niveau de séniorité : ${level || "À définir"}`,
    `- Compétences requises : ${skillsLine}`,
    `- Période concernée : ${sprintLabel}`,
    "",
    "Pourriez-vous lancer une recherche pour ce profil ? Je reste à votre disposition pour en discuter.",
    "",
    "Cordialement,",
    pmName ? pmName : "Le PM",
  ];
  return lines.join("\n");
}


function EmailChipsInput({ value, onChange, placeholder, label, suggestions = [] }) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState(null);
  const [open, setOpen]   = useState(false);
  const wrapRef = useRef(null);

  // Fermer le dropdown si clic à l'extérieur.
  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Suggestions filtrées par draft, en excluant celles déjà sélectionnées.
  const filteredSuggestions = useMemo(() => {
    const term = draft.trim().toLowerCase();
    return (suggestions ?? [])
      .filter((s) => !value.includes(s.email))
      .filter((s) => !term || s.name?.toLowerCase().includes(term) || s.email?.toLowerCase().includes(term))
      .slice(0, 8);
  }, [suggestions, draft, value]);

  const addEmail = (email) => {
    const v = (email ?? draft).trim();
    if (!v) return;
    if (!isValidEmail(v)) { setError("Adresse email invalide"); return; }
    if (value.includes(v)) { setError("Déjà dans la liste"); return; }
    onChange([...value, v]);
    setDraft("");
    setError(null);
  };

  const remove = (e) => onChange(value.filter((x) => x !== e));

  return (
    <div ref={wrapRef} className="relative">
      <label className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold block mb-1">
        {label}
      </label>
      <div
        className="flex flex-wrap items-center gap-1 px-2 py-1.5 rounded-lg border border-slate-200 bg-white focus-within:border-navy/40 focus-within:ring-2 focus-within:ring-navy/10"
        onClick={() => setOpen(true)}
      >
        {value.map((e) => {
          const meta = suggestions.find((s) => s.email === e);
          return (
            <span
              key={e}
              className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full border bg-violet-50 text-violet-700 border-violet-200"
              title={meta?.name ? `${meta.name} <${e}>` : e}
            >
              {meta?.name ? `${meta.name}` : e}
              <button
                type="button"
                onClick={(ev) => { ev.stopPropagation(); remove(e); }}
                className="hover:text-rose-500"
              >
                <X size={10} />
              </button>
            </span>
          );
        })}
        <input
          type="email"
          value={draft}
          onChange={(ev) => { setDraft(ev.target.value); setError(null); setOpen(true); }}
          onKeyDown={(ev) => {
            if (ev.key === "Enter" || ev.key === ",") { ev.preventDefault(); addEmail(); }
            if (ev.key === "Backspace" && !draft && value.length) onChange(value.slice(0, -1));
            if (ev.key === "Escape") setOpen(false);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => addEmail(), 150)}  // léger délai pour laisser le clic dropdown se faire
          placeholder={value.length ? "" : placeholder}
          className="flex-1 min-w-[120px] text-xs outline-none bg-transparent"
        />
      </div>

      {/* Dropdown suggestions style Gmail */}
      {open && filteredSuggestions.length > 0 && (
        <div className="absolute z-30 left-0 right-0 mt-1 rounded-lg border border-slate-200 bg-white shadow-lg overflow-hidden">
          <div className="px-3 py-1.5 text-[9px] uppercase tracking-wide text-slate-400 font-semibold border-b border-slate-100 bg-slate-50 flex items-center gap-1">
            <Users size={10} /> Contacts RH
          </div>
          {filteredSuggestions.map((s) => (
            <button
              key={s.email}
              type="button"
              onMouseDown={(ev) => { ev.preventDefault(); addEmail(s.email); }}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-violet-50 transition-colors flex items-center gap-2"
            >
              <div className="w-6 h-6 rounded-full bg-violet-100 text-violet-700 flex items-center justify-center text-[10px] font-bold shrink-0">
                {s.name?.[0]?.toUpperCase() ?? "?"}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-slate-700 truncate">{s.name}</p>
                <p className="text-[10px] text-slate-500 truncate">{s.email}</p>
              </div>
            </button>
          ))}
        </div>
      )}

      {error && <p className="text-[10px] text-rose-600 mt-0.5">{error}</p>}
    </div>
  );
}


export default function RecruitmentRequestDialog({
  open,
  onClose,
  projectId,
  projectName,
  profile,
  requiredSkills = [],
  requiredLevel,
  sprintNumber,
  sprintStart,
  sprintEnd,
  pmName,
  onSent,
}) {
  const sprintLabel = useMemo(() => {
    if (!sprintNumber) return "—";
    if (sprintStart && sprintEnd) return `Sprint ${sprintNumber} (${sprintStart} → ${sprintEnd})`;
    return `Sprint ${sprintNumber}`;
  }, [sprintNumber, sprintStart, sprintEnd]);

  const [to,      setTo]      = useState([]);
  const [cc,      setCc]      = useState([]);
  const [subject, setSubject] = useState("");
  const [body,    setBody]    = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error,   setError]   = useState(null);
  const [success, setSuccess] = useState(false);

  // Contacts RH récupérés depuis la DB (users role='rh' actifs).
  const [hrContacts, setHrContacts]     = useState([]);
  const [loadingHr,   setLoadingHr]     = useState(false);
  const [hrLoadError, setHrLoadError]   = useState(null);

  // Charger les contacts RH à l'ouverture du dialog (1 seule fois par ouverture).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingHr(true);
    setHrLoadError(null);
    getHrContacts()
      .then((contacts) => {
        if (cancelled) return;
        setHrContacts(contacts ?? []);
        // Pré-remplir le champ "À" avec TOUS les contacts RH actifs.
        setTo((contacts ?? []).map((c) => c.email).filter(Boolean));
      })
      .catch((e) => {
        if (cancelled) return;
        console.error("[RecruitmentRequestDialog] getHrContacts failed", e);
        setHrLoadError(
          e?.response?.data?.detail
          ?? "Impossible de charger les contacts RH. Saisis manuellement les destinataires."
        );
        setTo([]);
      })
      .finally(() => { if (!cancelled) setLoadingHr(false); });
    return () => { cancelled = true; };
  }, [open]);

  // Pré-remplir sujet / corps / cc à l'ouverture (indépendant du fetch HR)
  useEffect(() => {
    if (!open) return;
    setCc([]);
    setSubject(buildDefaultSubject(profile ?? "—", projectName ?? "—"));
    setBody(buildDefaultBody({
      profile:    profile ?? "—",
      level:      requiredLevel,
      skills:     requiredSkills,
      projectName: projectName ?? "—",
      sprintLabel,
      pmName,
    }));
    setError(null);
    setSuccess(false);
  }, [open, profile, projectName, requiredLevel, sprintLabel, pmName, requiredSkills]);

  if (!open) return null;

  const handleSend = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await sendRecruitmentRequest(projectId, {
        to,
        cc,
        subject,
        body,
        profile,
        required_skills: requiredSkills,
        required_level:  requiredLevel,
        sprint_number:   sprintNumber,
        sprint_start:    sprintStart,
        sprint_end:      sprintEnd,
      });
      setSuccess(true);
      onSent?.();
      // Petite latence pour montrer l'état "envoyé" avant de fermer.
      setTimeout(() => { onClose(); }, 800);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Échec de l'envoi de l'email.");
    } finally {
      setSubmitting(false);
    }
  };

  const canSend = to.length > 0 && subject.trim() && body.trim() && !submitting;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[92vh] overflow-hidden flex flex-col border border-slate-200">

        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-200 flex items-start justify-between gap-3 bg-gradient-to-r from-violet-50 to-violet-100/50">
          <div className="min-w-0 flex items-start gap-3">
            <div className="w-9 h-9 rounded-full bg-violet-600 text-white flex items-center justify-center shrink-0">
              <Mail size={16} />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-slate-800">
                Signaler un besoin en recrutement
              </h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Email à l'équipe RH — projet « {projectName} »
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="p-1 rounded-lg hover:bg-white/80 text-slate-500 disabled:opacity-50"
          >
            <X size={18} />
          </button>
        </div>

        {/* Récap métier */}
        <div className="px-5 py-3 border-b border-slate-200 bg-slate-50/60 grid grid-cols-2 gap-2 text-[11px]">
          <div>
            <p className="text-[9px] uppercase text-slate-400 font-semibold">Profil</p>
            <p className="font-semibold text-slate-700 truncate">{profile}</p>
          </div>
          <div>
            <p className="text-[9px] uppercase text-slate-400 font-semibold">Séniorité</p>
            <p className="font-semibold text-slate-700">{requiredLevel ?? "—"}</p>
          </div>
          <div className="col-span-2">
            <p className="text-[9px] uppercase text-slate-400 font-semibold">Période</p>
            <p className="font-semibold text-slate-700">{sprintLabel}</p>
          </div>
          {requiredSkills?.length > 0 && (
            <div className="col-span-2">
              <p className="text-[9px] uppercase text-slate-400 font-semibold mb-1">Compétences requises</p>
              <div className="flex flex-wrap gap-1">
                {requiredSkills.map((s) => (
                  <span
                    key={s}
                    className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 font-medium"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Form */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {loadingHr && (
            <p className="text-[11px] text-slate-500 flex items-center gap-1.5">
              <Loader size={11} className="animate-spin" />
              Chargement des contacts RH…
            </p>
          )}
          {hrLoadError && (
            <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
              {hrLoadError}
            </p>
          )}
          {!loadingHr && !hrLoadError && hrContacts.length === 0 && (
            <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
              Aucun utilisateur avec le rôle <strong>RH</strong> n'a été trouvé. Saisis manuellement les destinataires.
            </p>
          )}
          <EmailChipsInput
            label={`À${hrContacts.length ? ` (${hrContacts.length} contact${hrContacts.length > 1 ? "s" : ""} RH pré-remplis)` : ""}`}
            value={to}
            onChange={setTo}
            placeholder="email@talan.com"
            suggestions={hrContacts}
          />
          <EmailChipsInput
            label="CC (optionnel)"
            value={cc}
            onChange={setCc}
            placeholder="manager@talan.com, …"
            suggestions={hrContacts}
          />
          <div>
            <label className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold block mb-1">Sujet</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 outline-none focus:border-navy/40 focus:ring-2 focus:ring-navy/10"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold block mb-1">Message</label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={11}
              className="w-full px-2.5 py-2 text-xs rounded-lg border border-slate-200 outline-none focus:border-navy/40 focus:ring-2 focus:ring-navy/10 font-mono leading-relaxed resize-y"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-200 flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            {error && (
              <p className="text-xs text-rose-600 truncate">{error}</p>
            )}
            {success && (
              <p className="text-xs text-emerald-600 font-medium">Email envoyé à l'équipe RH ✓</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
            >
              Annuler
            </button>
            <button
              type="button"
              onClick={handleSend}
              disabled={!canSend}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-violet-600 text-white text-xs font-medium hover:bg-violet-700 disabled:opacity-50 transition-colors"
            >
              {submitting ? <Loader size={12} className="animate-spin" /> : <Send size={12} />}
              {submitting ? "Envoi…" : "Envoyer la demande"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
