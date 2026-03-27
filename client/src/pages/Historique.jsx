// src/pages/Historique.jsx
import { useState, useEffect } from "react";
import { useChatStore } from "../store";
import { useNavigate } from "react-router-dom";
import {
  Search,
  RotateCcw,
  ChevronRight,
  MessageSquare,
  Calendar,
  Palmtree,
  ExternalLink,
  MapPin,
  Users,
  Loader,
} from "lucide-react";
import clsx from "clsx";
import api from "../api";

const AGENT_COLORS = {
  RH: "bg-green-100 text-green-700",
  CRM: "bg-blue-100 text-blue-700",
  Jira: "bg-orange-100 text-orange-700",
  Slack: "bg-purple-100 text-purple-700",
  Calendar: "bg-cyan-100 text-cyan-700",
};

const TABS = [
  { id: "conversations", label: "Conversations", icon: MessageSquare },
  { id: "calendar", label: "Événements", icon: Calendar },
  { id: "leaves", label: "Congés", icon: Palmtree },
];

const CONV_FILTERS = [
  "Tout",
  "Cette semaine",
  "Ce mois",
  "RH",
  "CRM",
  "Jira",
  "Slack",
  "Calendar",
];

/* ════════════════════════════════════════════════════
   FORMAT HELPERS
   ════════════════════════════════════════════════════ */
function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function fmtRelative(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now - d;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "à l'instant";
  if (diffMin < 60) return `il y a ${diffMin} min`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `il y a ${diffH}h`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `il y a ${diffD}j`;
  return fmtDate(iso);
}

/* ════════════════════════════════════════════════════
   CONVERSATIONS TAB (existant, inchangé)
   ════════════════════════════════════════════════════ */
function ConversationsTab() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("Tout");
  const [expanded, setExpanded] = useState(null);
  const { conversations, setActive } = useChatStore();
  const nav = useNavigate();

  const filtered = conversations.filter((c) => {
    const matchSearch = c.title.toLowerCase().includes(search.toLowerCase());
    const matchFilter =
      filter === "Tout" ||
      c.agents.includes(filter) ||
      filter === "Cette semaine" ||
      filter === "Ce mois";
    return matchSearch && matchFilter;
  });

  return (
    <>
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            className="input-field pl-9"
            placeholder="Rechercher dans l'historique..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="flex gap-2 mb-5 overflow-x-auto pb-1">
        {CONV_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={clsx(
              "shrink-0 text-xs px-3 py-1.5 rounded-lg font-medium transition-all",
              filter === f
                ? "bg-navy text-white"
                : "bg-white border border-slate-200 text-slate-600 hover:border-cyan"
            )}
          >
            {f}
          </button>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-16">
          <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Search size={22} className="text-slate-400" />
          </div>
          <p className="text-slate-500">Aucune conversation trouvée</p>
        </div>
      )}

      <div className="space-y-3">
        {filtered.map((conv) => (
          <div key={conv.id} className="card overflow-hidden">
            <div
              className="p-4 flex items-center gap-4 cursor-pointer hover:bg-slate-50 transition-colors"
              onClick={() =>
                setExpanded(expanded === conv.id ? null : conv.id)
              }
            >
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-800 text-sm truncate mb-1">
                  {conv.title}
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400">{conv.date}</span>
                  <span className="text-xs text-slate-400">
                    {conv.messageCount} messages
                  </span>
                  <div className="flex gap-1">
                    {conv.agents.map((a) => (
                      <span
                        key={a}
                        className={clsx(
                          "text-xs px-1.5 py-0.5 rounded-md font-medium",
                          AGENT_COLORS[a] || "bg-slate-100 text-slate-600"
                        )}
                      >
                        {a}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setActive(conv.id);
                    nav("/chat");
                  }}
                  className="text-xs btn-secondary py-1.5 px-3 flex items-center gap-1"
                >
                  <RotateCcw size={12} /> Reprendre
                </button>
                <ChevronRight
                  size={16}
                  className={clsx(
                    "text-slate-400 transition-transform",
                    expanded === conv.id && "rotate-90"
                  )}
                />
              </div>
            </div>

            {expanded === conv.id && (
              <div className="border-t border-slate-100 p-4 bg-slate-50 space-y-3">
                {conv.messages.map((msg, i) => (
                  <div
                    key={i}
                    className={clsx(
                      "flex gap-2",
                      msg.role === "user" && "flex-row-reverse"
                    )}
                  >
                    <div
                      className={clsx(
                        "text-xs px-3 py-2 rounded-xl max-w-md",
                        msg.role === "user"
                          ? "bg-navy text-white"
                          : "bg-white border border-slate-200 text-slate-700"
                      )}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

/* ════════════════════════════════════════════════════
   CALENDAR TAB — événements + historique actions
   ════════════════════════════════════════════════════ */
function CalendarTab() {
  const [events, setEvents] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [evRes, hRes] = await Promise.all([
          api.get("/events/"),
          api.get("/events/history"),
        ]);
        setEvents(evRes.data);
        setHistory(hRes.data);
      } catch (err) {
        console.error("Erreur chargement événements:", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 gap-2 text-slate-400">
        <Loader size={16} className="animate-spin" /> Chargement...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Mes événements */}
      <div>
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Calendar size={14} className="text-cyan" />
          Mes événements ({events.length})
        </h3>
        {events.length === 0 ? (
          <p className="text-sm text-slate-400 italic">
            Aucun événement créé via l'assistant.
          </p>
        ) : (
          <div className="space-y-2">
            {events.map((evt) => (
              <div
                key={evt.id}
                className="card p-4 flex items-start gap-4 hover:shadow-md transition-shadow"
              >
                {/* Indicateur date */}
                <div className="w-14 text-center shrink-0">
                  <div className="text-xs font-semibold text-cyan uppercase">
                    {new Date(evt.start).toLocaleDateString("fr-FR", {
                      month: "short",
                    })}
                  </div>
                  <div className="text-2xl font-bold text-navy leading-tight">
                    {new Date(evt.start).getDate()}
                  </div>
                </div>

                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-800 text-sm truncate">
                    {evt.title}
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {fmtTime(evt.start)} — {fmtTime(evt.end)}
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {evt.location && (
                      <span className="inline-flex items-center gap-1 text-xs bg-orange-50 text-orange-600 px-2 py-0.5 rounded-md">
                        <MapPin size={10} /> {evt.location}
                      </span>
                    )}
                    {evt.attendees.length > 0 && (
                      <span className="inline-flex items-center gap-1 text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-md">
                        <Users size={10} /> {evt.attendees.length} participant
                        {evt.attendees.length > 1 ? "s" : ""}
                      </span>
                    )}
                    {evt.meet_link && (
                      <span className="inline-flex items-center gap-1 text-xs bg-green-50 text-green-600 px-2 py-0.5 rounded-md">
                        Google Meet
                      </span>
                    )}
                  </div>
                </div>

                {evt.html_link && (
                  <a
                    href={evt.html_link}
                    target="_blank"
                    rel="noreferrer"
                    className="text-slate-400 hover:text-cyan transition-colors shrink-0"
                  >
                    <ExternalLink size={14} />
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Timeline des actions */}
      <div>
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          Historique des actions
        </h3>
        {history.length === 0 ? (
          <p className="text-sm text-slate-400 italic">
            Aucune action enregistrée.
          </p>
        ) : (
          <div className="relative pl-6 border-l-2 border-slate-200 space-y-4">
            {history.map((log) => (
              <div key={log.id} className="relative">
                {/* Point sur la timeline */}
                <div
                  className={clsx(
                    "absolute -left-[25px] w-4 h-4 rounded-full border-2 border-white flex items-center justify-center text-[8px]",
                    log.action === "created" && "bg-green-400",
                    log.action === "updated" && "bg-blue-400",
                    log.action === "updated_schedule" && "bg-amber-400",
                    log.action === "deleted" && "bg-red-400"
                  )}
                />
                <div className="bg-white border border-slate-100 rounded-xl p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm">{log.icon}</span>
                    <span className="text-xs font-semibold text-slate-700">
                      {log.event_title}
                    </span>
                    <span className="ml-auto text-xs text-slate-400">
                      {fmtRelative(log.created_at)}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">{log.description}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════
   LEAVES TAB — historique congés
   ════════════════════════════════════════════════════ */
function LeavesTab() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await api.get("/events/leaves/history");
        setHistory(res.data);
      } catch (err) {
        console.error("Erreur chargement historique congés:", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 gap-2 text-slate-400">
        <Loader size={16} className="animate-spin" /> Chargement...
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="text-center py-16">
        <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <Palmtree size={22} className="text-slate-400" />
        </div>
        <p className="text-slate-500">Aucune action de congé enregistrée.</p>
      </div>
    );
  }

  return (
    <div className="relative pl-6 border-l-2 border-slate-200 space-y-4">
      {history.map((log) => (
        <div key={log.id} className="relative">
          <div
            className={clsx(
              "absolute -left-[25px] w-4 h-4 rounded-full border-2 border-white",
              log.action === "requested" && "bg-amber-400",
              log.action === "approved" && "bg-green-400",
              log.action === "rejected" && "bg-red-400",
              log.action === "cancelled" && "bg-slate-400"
            )}
          />
          <div className="bg-white border border-slate-100 rounded-xl p-3">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm">{log.icon}</span>
              <span className="text-xs font-semibold text-slate-700 capitalize">
                {log.action === "requested"
                  ? "Demande"
                  : log.action === "approved"
                    ? "Approuvé"
                    : log.action === "rejected"
                      ? "Refusé"
                      : "Annulé"}
              </span>
              <span className="ml-auto text-xs text-slate-400">
                {fmtRelative(log.created_at)}
              </span>
            </div>
            <p className="text-xs text-slate-500">{log.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ════════════════════════════════════════════════════
   PAGE PRINCIPALE
   ════════════════════════════════════════════════════ */
export default function Historique() {
  const [tab, setTab] = useState("conversations");

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Onglets */}
      <div className="flex gap-1 mb-6 bg-slate-100 rounded-xl p-1">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={clsx(
              "flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all",
              tab === id
                ? "bg-white text-navy shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            )}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Contenu */}
      {tab === "conversations" && <ConversationsTab />}
      {tab === "calendar" && <CalendarTab />}
      {tab === "leaves" && <LeavesTab />}
    </div>
  );
}
