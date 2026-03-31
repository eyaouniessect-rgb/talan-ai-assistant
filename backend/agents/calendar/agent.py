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
from app.core.groq_client import build_llm, rotate_llm_key, _is_fallback_error, _is_quota_error, FRIENDLY_QUOTA_MSG
from app.core.rbac import check_tool_permission, tool_permission_denied_message
from langsmith import trace


# ── Rôle et user courants (injectés par execute()) ───────
_current_role    = "consultant"
_current_user_id: int | None = None


def _extract_role_from_message(text: str) -> str:
    """Extrait le rôle du message enrichi envoyé par node3."""
    for line in text.split("\n"):
        if line.strip().lower().startswith("role utilisateur"):
            role = line.split(":")[-1].strip().lower()
            if role in ("consultant", "pm"):
                return role
    return "consultant"


def _extract_user_id_from_message(text: str) -> "int | None":
    """Extrait le user_id du message enrichi envoyé par node3."""
    for line in text.split("\n"):
        if line.strip().lower().startswith("user id"):
            try:
                return int(line.split(":")[-1].strip())
            except ValueError:
                return None
    return None


async def _log_calendar_action(
    employee_id: int,
    action: str,
    event_title: str,
    description: str,
    google_event_id: "str | None" = None,
    calendar_event_id: "int | None" = None,
) -> None:
    """Persiste une entrée dans hris.calendar_event_logs."""
    try:
        from app.database.connection import AsyncSessionLocal
        from app.database.models.hris import CalendarEventLog

        log = CalendarEventLog(
            employee_id       = employee_id,
            calendar_event_id = calendar_event_id,
            google_event_id   = google_event_id,
            event_title       = event_title,
            action            = action,
            description       = description,
        )
        async with AsyncSessionLocal() as session:
            session.add(log)
            await session.commit()
        print(f"  📋 Log calendar : [{action}] {event_title}")
    except Exception as e:
        print(f"  ⚠️ Impossible de logger l'action calendar : {e}")


async def _get_employee_id(user_id: int) -> "int | None":
    """Résout user_id → employee_id dans hris.employees."""
    try:
        from sqlalchemy import select
        from app.database.connection import AsyncSessionLocal
        from app.database.models.hris import Employee
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Employee.id).where(Employee.user_id == user_id)
            )
            row = result.scalar_one_or_none()
            return row
    except Exception as e:
        print(f"  ⚠️ _get_employee_id : {e}")
        return None


async def _get_saved_event_title(google_event_id: str) -> "str | None":
    """Récupère le titre d'un CalendarEvent depuis la DB via son google_event_id."""
    try:
        from sqlalchemy import select
        from app.database.connection import AsyncSessionLocal
        from app.database.models.hris import CalendarEvent

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CalendarEvent).where(CalendarEvent.google_event_id == google_event_id)
            )
            event = result.scalar_one_or_none()
            if event:
                return event.title
    except Exception:
        pass
    return None


async def _save_calendar_event(
    mcp_response: dict,
    employee_id: int,
    title: str,
    start_iso: str,
    end_iso: str,
    location: "str | None",
    attendees: "list[str] | None",
) -> "int | None":
    """Persiste un événement Google Calendar dans la table hris.calendar_events."""
    try:
        from datetime import datetime
        from app.database.connection import AsyncSessionLocal
        from app.database.models.hris import CalendarEvent

        raw = mcp_response.get("event", {}) or {}
        if isinstance(raw, dict) and "event" in raw:
            raw = raw["event"]

        google_event_id = raw.get("id")       if isinstance(raw, dict) else None
        html_link       = raw.get("htmlLink") if isinstance(raw, dict) else None
        meet_link       = raw.get("hangoutLink") if isinstance(raw, dict) else None

        def _parse_dt(iso: str) -> datetime:
            return datetime.fromisoformat(iso[:19])

        event = CalendarEvent(
            employee_id     = employee_id,
            google_event_id = google_event_id,
            title           = title,
            start_datetime  = _parse_dt(start_iso),
            end_datetime    = _parse_dt(end_iso),
            location        = location,
            attendees       = ", ".join(attendees) if attendees else None,
            meet_link       = meet_link,
            html_link       = html_link,
        )

        async with AsyncSessionLocal() as session:
            session.add(event)
            await session.commit()
            await session.refresh(event)
            saved_id = event.id

        print(f"  💾 CalendarEvent sauvegardé : '{title}' (employee_id={employee_id})")
        return saved_id
    except Exception as e:
        print(f"  ⚠️ Impossible de sauvegarder CalendarEvent : {e}")
        return None


async def _check_rbac(tool_name: str) -> str | None:
    """Vérifie RBAC. Retourne None si OK, sinon le message d'erreur."""
    if await check_tool_permission(_current_role, tool_name):
        return None
    msg = tool_permission_denied_message(tool_name)
    print(f"  🔒 RBAC refusé : {_current_role} → {tool_name}")
    return json.dumps({"error": msg, "rbac_denied": True}, ensure_ascii=False)


# ── TOOL WRAPPERS (avec RBAC) ────────────────────────

@tool
async def check_calendar_conflicts(start_date: str, end_date: str) -> str:
    """Vérifie les conflits/disponibilités entre deux dates."""
    denied = await _check_rbac("check_calendar_conflicts")
    if denied: return denied
    return json.dumps(await tools.check_calendar_conflicts(start_date, end_date), ensure_ascii=False)


@tool
async def get_calendar_events(start_date: str, end_date: str) -> str:
    """Retourne la liste des événements entre deux dates."""
    denied = await _check_rbac("get_calendar_events")
    if denied: return denied
    return json.dumps(await tools.get_calendar_events(start_date, end_date), ensure_ascii=False)


@tool
async def create_meeting(
    title: str,
    start_date: str,
    start_time: str,
    end_time: str,
    attendees: list[str] | None = None,
    add_meet: bool = False,
    location: str | None = None,
) -> str:
    """Crée un événement dans le calendrier. location = lieu physique si présentiel (ex: 'Building 2, Talan')."""
    denied = await _check_rbac("create_meeting")
    if denied: return denied
    start_iso = f"{start_date}T{start_time}:00"
    end_iso   = f"{start_date}T{end_time}:00"
    result = await tools.create_meeting(title, start_iso, end_iso, attendees=attendees, add_meet=add_meet, location=location)

    if result.get("success") and _current_user_id:
        employee_id = await _get_employee_id(_current_user_id)
        if employee_id:
            saved_id = await _save_calendar_event(result, employee_id, title, start_iso, end_iso, location, attendees)

            raw = result.get("event", {}) or {}
            if isinstance(raw, dict) and "event" in raw:
                raw = raw["event"]
            gid = raw.get("id") if isinstance(raw, dict) else None

            date_part = start_iso[:10]
            desc = f"Vous avez créé la réunion **{title}** le {date_part} de {start_time} à {end_time}"
            if location:
                desc += f" — lieu : {location}"
            if attendees:
                desc += f" — participants : {', '.join(attendees)}"

            await _log_calendar_action(
                employee_id       = employee_id,
                action            = "created",
                event_title       = title,
                description       = desc,
                google_event_id   = gid,
                calendar_event_id = saved_id,
            )

    return json.dumps(result, ensure_ascii=False)


@tool
async def update_meeting(
    event_id: str,
    title: str | None = None,
    start_date: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    attendees: list[str] | None = None,
    remove_meet: bool = False,
    location: str | None = None,
) -> str:
    """
    Met à jour un événement existant (titre, heure, participants, lien Meet, lieu).
    remove_meet=True : supprime le lien Google Meet de la réunion (passage en présentiel).
    location : lieu physique à ajouter/modifier (ex: 'Building 2, Talan').
    """
    denied = await _check_rbac("update_meeting")
    if denied: return denied
    start_iso = f"{start_date}T{start_time}:00" if start_date and start_time else None
    end_iso   = f"{start_date}T{end_time}:00"   if start_date and end_time   else None
    result = await tools.update_meeting(
        event_id, title=title, start=start_iso, end=end_iso,
        attendees=attendees, remove_meet=remove_meet, location=location,
    )

    if result.get("success") and _current_user_id:
        employee_id = await _get_employee_id(_current_user_id)
        if employee_id:
            saved_title = title or await _get_saved_event_title(event_id) or event_id

            changes = []
            if start_date and start_time:
                changes.append(f"nouvelle date : {start_date} de {start_time} à {end_time or '?'}")
            if title:
                changes.append(f"nouveau titre : **{title}**")
            if location:
                changes.append(f"nouveau lieu : {location}")
            if attendees is not None:
                changes.append("participants mis à jour")
            if remove_meet:
                changes.append("lien Google Meet supprimé")

            change_str   = " — ".join(changes) if changes else "modifications appliquées"
            action_label = "updated_schedule" if (start_date and start_time and not title and not location) else "updated"
            desc         = f"Vous avez {'décalé' if action_label == 'updated_schedule' else 'modifié'} la réunion **{saved_title}** — {change_str}"

            await _log_calendar_action(
                employee_id     = employee_id,
                action          = action_label,
                event_title     = saved_title,
                description     = desc,
                google_event_id = event_id,
            )

    return json.dumps(result, ensure_ascii=False)


@tool
async def delete_meeting(event_id: str) -> str:
    """Supprime un événement du calendrier."""
    denied = await _check_rbac("delete_meeting")
    if denied: return denied
    saved_title = await _get_saved_event_title(event_id) or event_id
    result = await tools.delete_meeting(event_id)

    if result.get("success") and _current_user_id:
        employee_id = await _get_employee_id(_current_user_id)
        if employee_id:
            await _log_calendar_action(
                employee_id     = employee_id,
                action          = "deleted",
                event_title     = saved_title,
                description     = f"Vous avez supprimé la réunion **{saved_title}**",
                google_event_id = event_id,
            )

    return json.dumps(result, ensure_ascii=False)


@tool
async def search_meetings(query: str) -> str:
    """Recherche des événements par mot-clé."""
    denied = await _check_rbac("search_meetings")
    if denied: return denied
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
        global _current_role, _current_user_id

        user_input = context.get_user_input()
        _current_role    = _extract_role_from_message(user_input)
        _current_user_id = _extract_user_id_from_message(user_input)

        print(f"\n{'='*50}")
        print(f"📅 CalendarAgent — Message reçu : {user_input[:200]}")
        print(f"🔐 Rôle utilisateur : {_current_role}")
        print(f"{'='*50}")

        max_retries = 3
        result = None

        with trace(
            name="calendar_agent.execute",
            run_type="chain",
            inputs={"user_input": user_input[:1000], "role": _current_role, "user_id": _current_user_id},
            tags=["agent", "calendar"],
        ) as ls_run:
            for attempt in range(max_retries):
                try:
                    result = await self.react_agent.ainvoke({
                        "messages": [HumanMessage(content=user_input)]
                    })
                    break

                except Exception as e:
                    if _is_quota_error(e):
                        print(f"⚠️ Quota tokens dépassé (Calendar) : {str(e)[:120]}")
                        ls_run.end(outputs={"response": FRIENDLY_QUOTA_MSG, "error": "quota"})
                        response = json.dumps({
                            "response": FRIENDLY_QUOTA_MSG,
                            "react_steps": [],
                        }, ensure_ascii=False)
                        message = new_agent_text_message(response)
                        await event_queue.enqueue_event(message)
                        return
                    elif _is_fallback_error(e) and rotate_llm_key():
                        print(f"⚠️ Clé Groq échouée (tentative {attempt+1}/{max_retries}) → rotation vers clé suivante")
                        self._build_react_agent()
                        continue

                    print(f"❌ Erreur (tentative {attempt+1}) : {str(e)}")
                    if attempt == max_retries - 1:
                        ls_run.end(outputs={"response": f"Erreur : {str(e)}", "error": str(e)})
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

            ls_run.end(outputs={
                "response": final[:500],
                "react_steps": react_steps,
                "steps_count": len(react_steps),
                "ui_hint": ui_hint,
            })

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

    # ── Date + heure + emails (réunion avec participants) ──
    _needs_datetime = bool(re.search(
        r"quelle heure|a quelle heure|heure.*(debut|fin)|debut et fin"
        r"|date.{0,15}(horaire|heure)|horaire.{0,15}souhait"
        r"|nouvelle date.{0,15}heur|preciser.{0,20}(date|heure|horaire)",
        t,
    ))
    _needs_emails = bool(re.search(
        r"e-mail|email|adresse mail|adresses mail|coordonnees|pouvez.vous me communiquer",
        t,
    ))
    if _needs_datetime and _needs_emails:
        return {"type": "event_datetime_with_emails"}

    # ── Date + heure début/fin (événements calendar) ─────
    if _needs_datetime:
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