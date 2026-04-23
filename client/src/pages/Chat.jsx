// src/pages/Chat.jsx
import { useState, useRef, useEffect } from "react";
import { useChatStore, useAuthStore } from "../store";
import {
  Send,
  Plus,
  ChevronDown,
  ChevronRight,
  Paperclip,
  Zap,
  CheckCircle,
  Loader,
  AlertTriangle,
  Calendar,
  Clock,
  Mail,
  X,
  Users,
  Search,
  MessageSquare,
  Briefcase,
  Settings2,
  ArrowRight,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import clsx from "clsx";
import remarkGfm from "remark-gfm";

const AGENT_COLORS = {
  RH: "bg-green-100 text-green-700",
  CRM: "bg-blue-100 text-blue-700",
  Jira: "bg-orange-100 text-orange-700",
  Slack: "bg-purple-100 text-purple-700",
  Calendar: "bg-cyan-100 text-cyan-700",
};

const AGENT_ICON = {
  rh:       <Users size={12} />,
  calendar: <Calendar size={12} />,
  jira:     <Briefcase size={12} />,
  slack:    <MessageSquare size={12} />,
  crm:      <Settings2 size={12} />,
  chat:     <MessageSquare size={12} />,
};

const QUICK_CONSULTANT = [
  "Créer un congé",
  "Voir mes projets",
  "Statut de mes tickets Jira",
  "Mon calendrier cette semaine",
  "Chercher dans la documentation",
];
const QUICK_PM = [
  "Créer un nouveau projet",
  "Rapport client",
  "Disponibilité de l'équipe",
  "Voir tous les tickets Jira",
  "Uploader un CDC",
];

function formatAssistantContent(content = "") {
  // Replace long raw Google Calendar URLs with short markdown links for better layout.
  return content.replace(
    /(https?:\/\/www\.google\.com\/calendar\/event\?eid=[^\s\]\)]+)/g,
    "[Ouvrir l'evenement]($1)",
  );
}

function StepStatusIcon({ status }) {
  if (status === "done")
    return <CheckCircle size={13} className="text-green-500 shrink-0" />;
  if (status === "running")
    return <Loader size={13} className="text-cyan animate-spin shrink-0" />;
  if (status === "unavailable")
    return <AlertTriangle size={13} className="text-orange-400 shrink-0" />;
  if (status === "skipped")
    return <span className="w-3 h-3 shrink-0 text-slate-300 text-xs leading-none">—</span>;
  if (status === "waiting")
    return <Clock size={13} className="text-yellow-400 shrink-0" />;
  return <Loader size={13} className="text-slate-300 shrink-0" />;
}

function ThinkingCard({ steps, streaming }) {
  const [open, setOpen] = useState(true);
  if (!steps || steps.length === 0) return null;

  const finishedCount = steps.filter(
    (s) => s.status === "done" || s.status === "unavailable" || s.status === "skipped"
  ).length;

  return (
    <div className="border border-cyan/30 bg-cyan/5 rounded-xl mb-3 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-4 py-2.5 text-left hover:bg-cyan/10 transition-colors"
      >
        {open ? (
          <ChevronDown size={15} className="text-cyan shrink-0" />
        ) : (
          <ChevronRight size={15} className="text-cyan shrink-0" />
        )}
        <span className="text-xs font-semibold text-cyan">Étapes de traitement</span>
        {streaming && (
          <Loader size={12} className="text-cyan animate-spin shrink-0" />
        )}
        <span className="ml-auto text-xs text-slate-400">
          {finishedCount}/{steps.length}
        </span>
      </button>

      {open && (
        <div className="px-4 pb-3 pt-1 space-y-2 border-t border-cyan/20">
          {steps.map((step, i) => {
            const agentIcon = AGENT_ICON[step.agent] ?? <Search size={12} />;
            const history = step.history;
            const hasHistory = history && history.length > 1;

            return (
              <div key={step.step_id || i} className="flex flex-col gap-0.5">
                {/* Ligne principale de l'étape */}
                <div className="thinking-step">
                  <StepStatusIcon status={step.status} />
                  {/* Icône agent */}
                  <span className="text-slate-400 shrink-0">{agentIcon}</span>
                  <span className={`text-xs font-medium ${
                    step.status === "done" ? "text-slate-600" :
                    step.status === "running" ? "text-cyan-700" :
                    step.status === "unavailable" ? "text-orange-500" :
                    step.status === "waiting" ? "text-yellow-600" :
                    "text-slate-400"
                  }`}>
                    {step.text}
                  </span>
                </div>

                {/* Historique des tool calls (affiché sous l'étape principale) */}
                {hasHistory && (
                  <div className="ml-6 flex flex-col gap-0.5 border-l-2 border-cyan/20 pl-3">
                    {history.map((h, hi) => (
                      <div key={hi} className="flex items-center gap-1.5">
                        <ArrowRight size={10} className="text-slate-300 shrink-0" />
                        <span className={`text-xs ${
                          hi === history.length - 1 && step.status === "running"
                            ? "text-cyan-600 font-medium"
                            : "text-slate-400"
                        }`}>
                          {h}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function InteractiveHint({ hint, onSend }) {
  const [date, setDate] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [timeStart, setTimeStart] = useState("");
  const [timeEnd, setTimeEnd] = useState("");
  const [emails, setEmails] = useState([""]);
  const [sent, setSent] = useState(false);

  if (!hint || sent) return null;

  // Calendar pickers are disabled in chat to avoid misplaced UI blocks.
  if (
    hint.type === "date_picker" ||
    hint.type === "event_datetime" ||
    hint.type === "event_datetime_with_emails"
  ) {
    return null;
  }

  const send = (text) => {
    setSent(true);
    onSend(text);
  };

  /* ── Sélection de channel Slack ─────────────────────── */
  if (hint.type === "channel_select") {
    return (
      <div className="mt-3 p-4 bg-gradient-to-br from-slate-50 to-cyan-50/30 border border-slate-200 rounded-2xl space-y-3 fade-in-up shadow-sm">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">
          <span className="text-base">#</span>
          Choisir un canal Slack
        </div>
        <div className="flex flex-wrap gap-2">
          {(hint.channels || []).map((ch) => (
            <button
              key={ch.id}
              onClick={() => send(`#${ch.name}`)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-sm text-slate-700 hover:border-cyan hover:text-cyan hover:bg-cyan/5 active:scale-95 transition-all shadow-sm font-medium"
            >
              <span className="text-slate-400">#</span>{ch.name}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const addEmail = () => setEmails((prev) => [...prev, ""]);
  const removeEmail = (i) =>
    setEmails((prev) => prev.filter((_, idx) => idx !== i));
  const updateEmail = (i, val) =>
    setEmails((prev) => prev.map((e, idx) => (idx === i ? val : e)));

  /* ── Date + heure + emails (réunion avec participants) ── */
  if (hint.type === "event_datetime_with_emails") {
    const validEmails = emails.filter((e) => e.trim());
    const canConfirm = date && timeStart && timeEnd;
    return (
      <div className="mt-3 p-4 bg-gradient-to-br from-slate-50 to-cyan-50/30 border border-slate-200 rounded-2xl space-y-4 fade-in-up shadow-sm">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">
          <Calendar size={14} className="text-cyan" />
          Choisir date, horaires et participants
        </div>

        {/* Date + heures */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400">Date</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400 flex items-center gap-1">
              <Clock size={11} /> Début
            </label>
            <input
              type="time"
              value={timeStart}
              onChange={(e) => setTimeStart(e.target.value)}
              className="border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white"
            />
          </div>
          <span className="text-slate-300 mt-5">→</span>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400 flex items-center gap-1">
              <Clock size={11} /> Fin
            </label>
            <input
              type="time"
              value={timeEnd}
              onChange={(e) => setTimeEnd(e.target.value)}
              className="border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white"
            />
          </div>
        </div>

        {/* Emails participants */}
        <div className="space-y-2">
          <label className="text-xs text-slate-400 flex items-center gap-1">
            <Mail size={11} /> E-mails des participants
          </label>
          {emails.map((email, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="email"
                value={email}
                onChange={(e) => updateEmail(i, e.target.value)}
                placeholder="prenom.nom@talan.com"
                className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white"
              />
              {emails.length > 1 && (
                <button
                  onClick={() => removeEmail(i)}
                  className="text-slate-400 hover:text-red-400 transition-colors"
                >
                  <X size={15} />
                </button>
              )}
            </div>
          ))}
          <button
            onClick={addEmail}
            className="flex items-center gap-1 text-xs text-cyan hover:text-cyan/80 transition-colors font-medium"
          >
            <Plus size={13} /> Ajouter un participant
          </button>
        </div>

        {canConfirm && (
          <button
            onClick={() => {
              const datePart = `le ${date} de ${timeStart} à ${timeEnd}`;
              const emailPart =
                validEmails.length > 0
                  ? `, participants: ${validEmails.join(", ")}`
                  : "";
              send(`${datePart}${emailPart}`);
            }}
            className="bg-cyan text-white px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-cyan/90 active:scale-95 transition-all shadow-md hover:shadow-cyan-200/50"
          >
            ✓ Confirmer
          </button>
        )}
      </div>
    );
  }

  /* ── Date + heure début/fin (événements) ────────────── */
  if (hint.type === "event_datetime") {
    const canConfirm = date && timeStart && timeEnd;
    return (
      <div className="mt-3 p-4 bg-gradient-to-br from-slate-50 to-cyan-50/30 border border-slate-200 rounded-2xl space-y-3 fade-in-up shadow-sm">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">
          <Calendar size={14} className="text-cyan" />
          Choisir date et horaires
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400">Date</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400 flex items-center gap-1">
              <Clock size={11} /> Début
            </label>
            <input
              type="time"
              value={timeStart}
              onChange={(e) => setTimeStart(e.target.value)}
              className="border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white"
            />
          </div>
          <span className="text-slate-300 mt-5">→</span>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400 flex items-center gap-1">
              <Clock size={11} /> Fin
            </label>
            <input
              type="time"
              value={timeEnd}
              onChange={(e) => setTimeEnd(e.target.value)}
              className="border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white"
            />
          </div>
        </div>
        {canConfirm && (
          <button
            onClick={() => send(`le ${date} de ${timeStart} à ${timeEnd}`)}
            className="bg-cyan text-white px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-cyan/90 active:scale-95 transition-all shadow-md hover:shadow-cyan-200/50"
          >
            ✓ Confirmer
          </button>
        )}
      </div>
    );
  }

  /* ── Date simple ────────────────────────────────────── */
  if (hint.type === "date_picker") {
    return (
      <div className="flex items-center gap-3 mt-3 fade-in-up">
        <div className="flex items-center gap-2 p-2.5 bg-gradient-to-br from-slate-50 to-cyan-50/30 border border-slate-200 rounded-xl shadow-sm">
          <Calendar size={14} className="text-cyan" />
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="border-none bg-transparent text-sm outline-none"
          />
        </div>
        {date && (
          <button
            onClick={() => send(date)}
            className="bg-cyan text-white px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-cyan/90 active:scale-95 transition-all shadow-md hover:shadow-cyan-200/50"
          >
            ✓ Confirmer
          </button>
        )}
      </div>
    );
  }

  /* ── Plage de dates (congés) ────────────────────────── */
  if (hint.type === "date_range") {
    return (
      <div className="mt-3 p-4 bg-gradient-to-br from-slate-50 to-cyan-50/30 border border-slate-200 rounded-2xl space-y-3 fade-in-up shadow-sm">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">
          <Calendar size={14} className="text-cyan" />
          Choisir la période
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400">Date début</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white"
            />
          </div>
          <span className="text-slate-300 mt-5">→</span>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400">Date fin</label>
            <input
              type="date"
              value={dateEnd}
              onChange={(e) => setDateEnd(e.target.value)}
              className="border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-cyan focus:ring-2 focus:ring-cyan/10 outline-none transition-all bg-white"
            />
          </div>
        </div>
        {date && dateEnd && (
          <button
            onClick={() => send(`du ${date} au ${dateEnd}`)}
            className="bg-cyan text-white px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-cyan/90 active:scale-95 transition-all shadow-md hover:shadow-cyan-200/50"
          >
            ✓ Confirmer
          </button>
        )}
      </div>
    );
  }

  return null;
}

function Message({ msg, isLast, onSend }) {
  const isUser = msg.role === "user";
  const assistantContent = !isUser
    ? formatAssistantContent(msg.content)
    : msg.content;
  return (
    <div
      className={clsx(
        "flex gap-3 mb-4 fade-in-up",
        isUser && "flex-row-reverse",
      )}
    >
      {!isUser && (
        <div className="w-8 h-8 bg-cyan rounded-xl flex items-center justify-center shrink-0 mt-1">
          <Zap size={14} className="text-white" />
        </div>
      )}
      <div className={clsx("flex flex-col max-w-2xl", isUser && "items-end")}>
        {!isUser && (
          <ThinkingCard steps={msg.steps} streaming={msg.streaming === true} />
        )}
        <div className={isUser ? "message-user" : "message-assistant"}>
          {isUser ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">
              {msg.content}
            </p>
          ) : msg.streaming && !msg.content ? (
            /* Spinner initial — avant que la première étape SSE n'arrive */
            <div className="flex items-center gap-2 py-1">
              <Loader size={14} className="text-cyan animate-spin shrink-0" />
              <span className="text-xs text-slate-400">
                L'assistant analyse votre demande...
              </span>
            </div>
          ) : (
            <div className="prose-chat">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ href, children, ...props }) => (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      {...props}
                    >
                      {children}
                    </a>
                  ),
                }}
              >
                {assistantContent}
              </ReactMarkdown>
            </div>
          )}
        </div>
        {!isUser && isLast && msg.ui_hint && !msg.streaming && (
          <InteractiveHint hint={msg.ui_hint} onSend={onSend} />
        )}
        <span className="text-xs text-slate-400 mt-1 px-1">{msg.time}</span>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-3 mb-4 fade-in-up">
      <div className="w-8 h-8 bg-cyan rounded-xl flex items-center justify-center shrink-0">
        <Zap size={14} className="text-white" />
      </div>
      <div className="message-assistant flex items-center gap-1 py-4">
        <div className="dot-loading">
          <span />
          <span />
          <span />
        </div>
        <span className="text-xs text-slate-400 ml-2">
          L'assistant analyse votre demande...
        </span>
      </div>
    </div>
  );
}

export default function Chat() {
  const [input, setInput] = useState("");
  const user = useAuthStore((s) => s.user);
  const {
    conversations,
    activeId,
    isTyping,
    setActive,
    newConversation,
    sendMessage,
    loadConversations,
  } = useChatStore();
  const bottomRef = useRef();
  const inputRef = useRef();
  const isPM = user?.role === "pm";
  const quick = isPM ? QUICK_PM : QUICK_CONSULTANT;
  const active = conversations.find((c) => c.id === activeId);

  // Détermine si un message est actuellement en streaming
  const hasStreamingMessage = active?.messages?.some((m) => m.streaming === true);

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active?.messages, isTyping]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [activeId]);

  const handleSend = () => {
    if (!input.trim()) return;
    sendMessage(input.trim());
    setInput("");
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full">
      {/* Liste des conversations */}
      <div className="w-72 border-r border-slate-100 bg-white flex-col shrink-0 hidden md:flex">
        <div className="p-4 border-b border-slate-100">
          <button
            onClick={newConversation}
            className="btn-cyan w-full flex items-center justify-center gap-2 text-sm"
          >
            <Plus size={16} /> Nouvelle conversation
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => setActive(conv.id)}
              className={clsx(
                "w-full text-left p-3 rounded-xl mb-1 transition-all hover:bg-slate-50",
                activeId === conv.id ? "bg-navy/5 border border-navy/10" : "",
              )}
            >
              <div className="text-sm font-medium text-slate-800 truncate mb-1">
                {conv.title}
              </div>
              <div className="text-[10px] text-slate-400 font-mono">
                ID: {conv.id > 1_000_000_000_000 ? `tmp_${String(conv.id).slice(-4)}` : conv.id}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">{conv.date}</span>
                <span className="text-xs text-slate-400">
                  {conv.messageCount} msg
                </span>
              </div>
              {conv.agents.length > 0 && (
                <div className="flex gap-1 mt-1.5 flex-wrap">
                  {conv.agents.map((a) => (
                    <span
                      key={a}
                      className={clsx(
                        "text-xs px-1.5 py-0.5 rounded-md font-medium",
                        AGENT_COLORS[a] || "bg-slate-100 text-slate-600",
                      )}
                    >
                      {a}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Zone de chat principale */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto p-6">
          {active?.messages?.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-16 h-16 bg-navy rounded-2xl flex items-center justify-center mb-4">
                <Zap size={28} className="text-cyan" />
              </div>
              <h3 className="font-display text-xl font-bold text-navy mb-2">
                Comment puis-je vous aider ?
              </h3>
              <p className="text-slate-500 text-sm mb-8 max-w-sm">
                Posez-moi une question ou choisissez une action rapide
                ci-dessous
              </p>
              <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                {quick.map((q) => (
                  <button
                    key={q}
                    onClick={() => setInput(q)}
                    className="text-sm bg-white border border-slate-200 hover:border-cyan hover:text-cyan px-4 py-2 rounded-xl transition-all"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {active?.messages?.map((msg, i) => (
            <Message
              key={i}
              msg={msg}
              isLast={i === active.messages.length - 1 && !isTyping}
              onSend={sendMessage}
            />
          ))}

          {/* TypingIndicator uniquement si pas encore de message streaming affiché */}
          {isTyping && !hasStreamingMessage && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>

        {active?.messages?.length > 0 && (
          <div className="px-6 pb-2 flex gap-2 overflow-x-auto">
            {quick.slice(0, 4).map((q) => (
              <button
                key={q}
                onClick={() => setInput(q)}
                className="shrink-0 text-xs bg-white border border-slate-200 hover:border-cyan hover:text-cyan px-3 py-1.5 rounded-lg transition-all whitespace-nowrap"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        <div className="p-4 border-t border-slate-100 bg-white">
          <div className="flex items-end gap-3 bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 focus-within:border-cyan focus-within:ring-2 focus-within:ring-cyan/10 transition-all">
            {isPM && (
              <button className="text-slate-400 hover:text-navy shrink-0 mb-0.5 transition-colors">
                <Paperclip size={19} />
              </button>
            )}
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Posez votre question..."
              rows={1}
              className="flex-1 bg-transparent outline-none text-sm text-slate-800 placeholder:text-slate-400 resize-none leading-relaxed"
              style={{ maxHeight: "120px", overflowY: "auto" }}
              onInput={(e) => {
                e.target.style.height = "auto";
                e.target.style.height = e.target.scrollHeight + "px";
              }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isTyping}
              className={clsx(
                "w-9 h-9 rounded-xl flex items-center justify-center shrink-0 transition-all",
                input.trim() && !isTyping
                  ? "bg-navy hover:bg-navy-light text-white"
                  : "bg-slate-200 text-slate-400 cursor-not-allowed",
              )}
            >
              <Send size={16} />
            </button>
          </div>
          <p className="text-xs text-slate-400 text-center mt-2">
            Entrée pour envoyer · Shift+Entrée pour nouvelle ligne
          </p>
        </div>
      </div>
    </div>
  );
}
