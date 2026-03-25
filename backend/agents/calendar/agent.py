# Logique ReAct de l'Agent Calendar.
# Logique ReAct de l'Agent Calendar.
import json
import re
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from a2a.server.agent_execution import AgentExecutor
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message
from agents.calendar.prompts import CALENDAR_REACT_PROMPT
from agents.calendar import tools
from app.core.groq_client import build_llm, rotate_llm_key, _is_fallback_error


# ── TOOL WRAPPERS ─────────────────────────

@tool
async def check_calendar_conflicts(start_date: str, end_date: str) -> str:
    """
    Vérifie les conflits dans le calendrier entre deux dates.
    Utilise Google Calendar (free/busy) pour détecter les créneaux occupés.
    
    Args:
        start_date (str): Date de début (ISO format YYYY-MM-DD ou datetime)
        end_date (str): Date de fin (ISO format YYYY-MM-DD ou datetime)

    Returns:
        JSON avec les créneaux occupés (conflicts)
    """
    return json.dumps(await tools.check_calendar_conflicts(start_date, end_date), ensure_ascii=False)


@tool
async def get_calendar_events(start_date: str, end_date: str) -> str:
    """
    Retourne la liste des événements du calendrier entre deux dates.
    
    Args:
        start_date (str): Date de début
        end_date (str): Date de fin

    Returns:
        JSON contenant les événements
    """
    return json.dumps(await tools.get_calendar_events(start_date, end_date), ensure_ascii=False)


@tool
async def create_meeting(
    title: str,
    start_date: str,
    start_time: str,
    end_time: str,
    attendees: list[str] | None = None,
    add_meet: bool = False,
) -> str:
    """
    Crée un événement dans le calendrier.

    Args:
        title (str): Titre de la réunion
        start_date (str): Date (YYYY-MM-DD)
        start_time (str): Heure de début (HH:MM)
        end_time (str): Heure de fin (HH:MM)
        attendees (list[str] | None): Liste d'emails des participants (optionnel)
        add_meet (bool): True pour générer un lien Google Meet (optionnel)

    Returns:
        JSON de l'événement créé
    """
    start_iso = f"{start_date}T{start_time}:00"
    end_iso = f"{start_date}T{end_time}:00"

    return json.dumps(
        await tools.create_meeting(title, start_iso, end_iso, attendees=attendees, add_meet=add_meet),
        ensure_ascii=False
    )


@tool
async def update_meeting(
    event_id: str,
    title: str | None = None,
    start_date: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    attendees: list[str] | None = None,
) -> str:
    """
    Met à jour un événement existant dans le calendrier.
    Peut modifier le titre, l'heure, et/ou la liste des participants.

    Args:
        event_id (str): ID de l'événement à modifier
        title (str | None): Nouveau titre (optionnel)
        start_date (str | None): Date YYYY-MM-DD (requis si changement d'heure)
        start_time (str | None): Nouvelle heure de début HH:MM (optionnel)
        end_time (str | None): Nouvelle heure de fin HH:MM (optionnel)
        attendees (list[str] | None): LISTE COMPLÈTE des emails après modification.
            Pour retirer quelqu'un : envoyer la liste sans son email.
            Pour ajouter quelqu'un : envoyer la liste avec le nouvel email.
            None = ne pas modifier les participants.

    Returns:
        JSON contenant l'événement mis à jour
    """
    start_iso = f"{start_date}T{start_time}:00" if start_date and start_time else None
    end_iso   = f"{start_date}T{end_time}:00"   if start_date and end_time   else None

    return json.dumps(
        await tools.update_meeting(event_id, title=title, start=start_iso, end=end_iso, attendees=attendees),
        ensure_ascii=False
    )


@tool
async def delete_meeting(event_id: str) -> str:
    """
    Supprime un événement du calendrier.
    
    Args:
        event_id (str): ID de l'événement à supprimer

    Returns:
        JSON confirmant la suppression
    """
    return json.dumps(await tools.delete_meeting(event_id), ensure_ascii=False)


@tool
async def search_meetings(query: str) -> str:
    """
    Recherche des événements dans le calendrier par mot-clé.
    
    Args:
        query (str): Texte de recherche

    Returns:
        JSON contenant les résultats trouvés
    """
    return json.dumps(await tools.search_meetings(query), ensure_ascii=False)


TOOLS = [
    check_calendar_conflicts,
    get_calendar_events,
    create_meeting,
    update_meeting,
    delete_meeting,
    search_meetings,
]


# ── EXECUTOR ─────────────────────────
class CalendarAgentExecutor(AgentExecutor):

    def __init__(self) -> None:
        self._build_react_agent()

    def _build_react_agent(self) -> None:
        llm = build_llm(
            model="openai/gpt-oss-120b",
            temperature=0,
            max_tokens=2048,
        )

        self.react_agent = create_react_agent(
            model=llm,
            tools=TOOLS,
            prompt=CALENDAR_REACT_PROMPT,
        )

    async def execute(self, context, event_queue):

        user_input = context.get_user_input()

        print(f"\n{'='*50}")
        print(f"📅 CalendarAgent — Message reçu : {user_input}")
        print(f"{'='*50}")

        max_retries = 3
        result = None

        for attempt in range(max_retries):
            try:
                result = await self.react_agent.ainvoke({
                    "messages": [HumanMessage(content=user_input)]
                })
                break

            except Exception as e:
                if _is_fallback_error(e) and rotate_llm_key():
                    print(f"⚠️ Clé Groq échouée (tentative {attempt+1}/{max_retries}) → rotation vers clé suivante")
                    self._build_react_agent()
                    continue

                print(f"❌ Erreur (tentative {attempt+1}) : {str(e)}")
                if attempt == max_retries - 1:
                    response = json.dumps({
                        "response": f"Erreur : {str(e)}",
                        "react_steps": []
                    }, ensure_ascii=False)

                    message = new_agent_text_message(response)
                    await event_queue.enqueue_event(message)
                    return

        # ── Extraction + Log Think/Act/Observe ───────────
        react_steps = []
        tool_calls_map = {}

        print(f"\n{'─'*50}")
        print("🧠 CYCLE ReAct — CalendarAgent :")

        for msg in result["messages"]:
            msg_type = type(msg).__name__

            if msg_type == "AIMessage":
                if msg.content:
                    print(f"  🤔 Think  : {msg.content[:300]}")
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        human_label = _tool_to_human_text(tc['name'], tc['args'])
                        react_steps.append(human_label)
                        tool_calls_map[tc['id']] = len(react_steps) - 1
                        print(f"  🔧 Act    : {tc['name']}({tc['args']})")

            elif msg_type == "ToolMessage":
                tool_call_id = getattr(msg, 'tool_call_id', None)
                obs_human = _format_observation(msg.content)
                print(f"  👁️  Observe: {msg.content[:200]}")
                if tool_call_id and tool_call_id in tool_calls_map:
                    idx = tool_calls_map[tool_call_id]
                    if obs_human:
                        react_steps[idx] += f"\n   → {obs_human}"

            elif msg_type == "HumanMessage":
                print(f"  👤 Human  : {msg.content[:200]}")

        print(f"{'─'*50}\n")

        final = result["messages"][-1].content

        ui_hint = _detect_ui_hint(final)
        print(f"  🎨 UI Hint détecté : {ui_hint}")
        response_data = {"response": final, "react_steps": react_steps}
        if ui_hint:
            response_data["ui_hint"] = ui_hint

        response = json.dumps(response_data, ensure_ascii=False)

        message = new_agent_text_message(response)
        await event_queue.enqueue_event(message)

    async def cancel(self, context, event_queue):
        pass


# ══════════════════════════════════════════════════════
# HELPERS — Affichage lisible pour l'Explainable AI
# ══════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    """Normalise les caractères Unicode exotiques produits par le LLM."""
    return (
        text.lower()
        .replace("\u2011", "-")   # non-breaking hyphen → -
        .replace("\u2010", "-")   # hyphen → -
        .replace("\u2013", "-")   # en-dash → -
        .replace("\u2014", "-")   # em-dash → -
        .replace("\u202f", " ")   # narrow no-break space → space
        .replace("\u00a0", " ")   # no-break space → space
        .replace("\u00ab", '"')   # «
        .replace("\u00bb", '"')   # »
    )


def _detect_ui_hint(text: str) -> "dict | None":
    """Analyse la réponse pour suggérer un composant UI interactif au frontend."""
    t = _normalize(text)

    # ── Choix en ligne / présentiel ──────────────────────
    if ("en ligne" in t or "presentiel" in t or "distanciel" in t) and "?" in t:
        return {
            "type": "choice",
            "options": [
                {"label": "En ligne (Google Meet)", "value": "oui, en ligne avec Google Meet", "icon": "video"},
                {"label": "Présentiel", "value": "non, en présentiel", "icon": "building"},
            ],
        }

    # ── Boutons Oui / Non ────────────────────────────────
    is_oui_non = (
        "souhaitez-vous" in t or
        "voulez-vous" in t or
        "confirmez-vous" in t or
        bool(re.search(r"oui\s*/\s*non", t)) or
        bool(re.search(r"r.pondez.*oui", t)) or
        ("oui" in t and "non" in t and "?" in t)
    )
    is_time_or_title = bool(re.search(r"quelle heure|quel titre|quel jour", t))
    if is_oui_non and not is_time_or_title:
        return {"type": "confirm", "options": ["Oui", "Non"]}

    # ── Date + heure début/fin (événements calendar) ─────
    if re.search(r"quelle heure|a quelle heure|heure.*(debut|fin)|debut et fin|date.{0,15}(horaire|heure)|horaire.{0,15}souhait|nouvelle date.{0,15}heur|preciser.{0,20}(date|heure|horaire)", t):
        return {"type": "event_datetime"}

    # ── Plage de dates ───────────────────────────────────
    if re.search(r"dates de (d.but|fin)|p.riode souhait.e|date de debut.*date de fin", t):
        return {"type": "date_range"}

    # ── Date simple ──────────────────────────────────────
    if re.search(r"quelle date|a quelle date|precisez la date|choisissez une date|quel jour|nouvelle date", t):
        return {"type": "date_picker"}

    return None


def _tool_to_human_text(tool_name: str, args: dict) -> str:
    """Convertit un appel d'outil en texte lisible pour l'utilisateur."""
    match tool_name:
        case "get_calendar_events":
            start = args.get("start_date", "")[:10]
            end   = args.get("end_date", "")[:10]
            if start == end:
                return f"📅 Consultation des événements du {start}..."
            return f"📅 Consultation des événements du {start} au {end}..."

        case "check_calendar_conflicts":
            start = args.get("start_date", "")[:10]
            end   = args.get("end_date", "")[:10]
            return f"🔍 Vérification des disponibilités du {start} au {end}..."

        case "search_meetings":
            return f"🔎 Recherche d'événements : « {args.get('query', '')} »..."

        case "create_meeting":
            title = args.get("title", "Sans titre")
            date  = args.get("start_date", "")
            start_t = args.get("start_time", "")
            return f"➕ Création de l'événement « {title} » le {date} à {start_t}..."

        case "update_meeting":
            parts = []
            if args.get("title"):
                parts.append(f"titre → « {args['title']} »")
            if args.get("start_time"):
                parts.append(f"heure → {args.get('start_time')}–{args.get('end_time', '?')}")
            detail = ", ".join(parts) if parts else "événement"
            return f"✏️ Modification : {detail}..."

        case "delete_meeting":
            return f"🗑️ Suppression de l'événement (ID: {args.get('event_id', '')[:8]}...)..."

        case _:
            return f"⚙️ {tool_name}..."


def _format_observation(content: str) -> str:
    """Convertit la réponse d'un outil en résumé lisible."""
    try:
        data = json.loads(content)

        # Résultat get_calendar_events / check_calendar_conflicts
        if "events" in data:
            events = data["events"]
            if not events:
                return "Aucun événement trouvé."
            summaries = [e.get("summary", "Sans titre") for e in events[:5]]
            return f"{len(events)} événement(s) trouvé(s) : {', '.join(summaries)}"

        # Résultat check_calendar_conflicts
        if "conflicts" in data:
            conflicts = data["conflicts"]
            if not conflicts:
                return "Aucun conflit — créneau libre ✅"
            titles = [c.get("title", "?") for c in conflicts[:3]]
            return f"{len(conflicts)} conflit(s) : {', '.join(titles)} ⚠️"

        # Résultat search_meetings
        if "results" in data:
            results = data["results"]
            if not results:
                return "Aucun résultat de recherche."
            summaries = [e.get("summary", "Sans titre") for e in results[:3]]
            return f"{len(results)} résultat(s) : {', '.join(summaries)}"

        # Résultat create / update / delete
        if data.get("success"):
            if "event" in data:
                raw = data["event"] or {}
                # MCP retourne parfois {"event": {"event": {...}}} — dénester
                if "event" in raw:
                    raw = raw["event"]
                title = raw.get("summary", "")
                start = (raw.get("start") or {}).get("dateTime", "")[:16].replace("T", " à ")
                link = raw.get("htmlLink", "")
                detail = f"« {title} »" + (f" — {start}" if start else "")
                if link:
                    detail += f" ([voir]({link}))"
                return f"Événement {detail} ✅"
            if "message" in data:
                return f"{data['message']} ✅"

        if "error" in data:
            return f"Erreur : {data['error']} ❌"

    except Exception:
        pass
    return ""