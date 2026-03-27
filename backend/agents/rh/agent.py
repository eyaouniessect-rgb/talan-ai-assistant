# agents/rh/agent.py
# ═══════════════════════════════════════════════════════════
# Agent RH — ReAct (GPT-OSS 120B) avec failover clés Groq
# ═══════════════════════════════════════════════════════════
from dotenv import load_dotenv
import json
from datetime import date

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.rh.prompts import RH_REACT_PROMPT
from agents.rh import tools as rh_tools
from app.core.groq_client import build_llm, rotate_llm_key, _is_fallback_error, _is_quota_error, FRIENDLY_QUOTA_MSG
from app.core.rbac import check_tool_permission, tool_permission_denied_message

load_dotenv()


# ── Rôle utilisateur courant (injecté par execute()) ─────
_current_role = "consultant"


async def _log_leave_action(
    user_id: int,
    action: str,
    description: str,
    leave_id: "int | None" = None,
) -> None:
    """Persiste une entrée dans hris.leave_logs via employee_id."""
    try:
        from sqlalchemy import select
        from app.database.connection import AsyncSessionLocal
        from app.database.models.hris import Employee, LeaveLog

        async with AsyncSessionLocal() as session:
            row = await session.execute(
                select(Employee.id).where(Employee.user_id == user_id)
            )
            employee_id = row.scalar_one_or_none()
            if not employee_id:
                return

            log = LeaveLog(
                employee_id = employee_id,
                leave_id    = leave_id,
                action      = action,
                description = description,
            )
            session.add(log)
            await session.commit()
        print(f"  📋 Log congé : [{action}] (employee_id={employee_id})")
    except Exception as e:
        print(f"  ⚠️ Impossible de logger l'action congé : {e}")


def _extract_role_from_message(text: str) -> str:
    """Extrait le rôle du message enrichi envoyé par node3."""
    for line in text.split("\n"):
        if line.strip().lower().startswith("role utilisateur"):
            role = line.split(":")[-1].strip().lower()
            if role in ("consultant", "pm"):
                return role
    return "consultant"


async def _check_rbac(tool_name: str) -> str | None:
    """Vérifie RBAC. Retourne None si OK, sinon le message d'erreur."""
    if await check_tool_permission(_current_role, tool_name):
        return None
    msg = tool_permission_denied_message(tool_name)
    print(f"  🔒 RBAC refusé : {_current_role} → {tool_name}")
    return json.dumps({"error": msg, "rbac_denied": True}, ensure_ascii=False)


# ══════════════════════════════════════════════════════
# OUTILS LANGCHAIN (avec RBAC)
# ══════════════════════════════════════════════════════

@tool
async def create_leave(user_id: int, start_date: str, end_date: str) -> str:
    """Crée une demande de congé. Vérifie automatiquement les chevauchements."""
    denied = await _check_rbac("create_leave")
    if denied: return denied
    result = await rh_tools.create_leave(user_id=user_id, start_date=start_date, end_date=end_date)

    if result.get("success"):
        leave_id = result.get("leave_id")
        days     = result.get("days_count", "?")
        await _log_leave_action(
            user_id     = user_id,
            action      = "requested",
            description = f"Vous avez demandé un congé du {start_date} au {end_date} ({days} jour(s))",
            leave_id    = leave_id,
        )

    return json.dumps(result, ensure_ascii=False)


@tool
async def get_my_leaves(user_id: int, status_filter: str = None) -> str:
    """Retourne les congés d'un employé."""
    denied = await _check_rbac("get_my_leaves")
    if denied: return denied
    result = await rh_tools.get_my_leaves(user_id=user_id, status_filter=status_filter)
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_team_availability(user_id: int) -> str:
    """Retourne la disponibilité de l'équipe."""
    denied = await _check_rbac("get_team_availability")
    if denied: return denied
    result = await rh_tools.get_team_availability(user_id=user_id)
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_team_stack(user_id: int) -> str:
    """Retourne les compétences techniques de l'équipe."""
    denied = await _check_rbac("get_team_stack")
    if denied: return denied
    result = await rh_tools.get_team_stack(user_id=user_id)
    return json.dumps(result, ensure_ascii=False)


@tool
async def check_calendar_conflicts(user_id: int, start_date: str, end_date: str) -> str:
    """Vérifie les conflits réels dans Google Calendar pour la période de congé donnée."""
    denied = await _check_rbac("check_calendar_conflicts")
    if denied: return denied
    try:
        from agents.calendar.tools import check_calendar_conflicts as cal_check
        result = await cal_check(start_date, end_date)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Calendar MCP indisponible : {e}")
        return json.dumps({
            "success": True,
            "conflicts": [],
            "message": "Impossible de vérifier le calendrier (service indisponible).",
            "mcp_error": True,
        }, ensure_ascii=False)


@tool
async def reschedule_meeting(
    event_id: str,
    event_title: str,
    current_start: str,
    current_end: str,
    new_date: str,
) -> str:
    """
    Replanifie une réunion via l'agent Calendar (A2A).
    Passe l'event_id directement pour éviter toute recherche par titre.

    event_id      : ID Google Calendar de l'événement (champ 'id' des conflicts).
    event_title   : titre de la réunion (pour le message de confirmation).
    current_start : début ISO actuel (ex: '2026-03-26T09:00:00+01:00').
    current_end   : fin ISO actuelle  (ex: '2026-03-26T10:00:00+01:00').
    new_date      : nouvelle date YYYY-MM-DD.
    """
    denied = await _check_rbac("reschedule_meeting")
    if denied: return denied
    from app.a2a.client import send_task
    today = date.today().strftime("%Y-%m-%d")
    # Reconstruit les heures de début/fin sur la nouvelle date
    new_start = new_date + current_start[10:]
    new_end   = new_date + current_end[10:]
    message = (
        f"Date du jour : {today}\n"
        f"Déplace l'événement avec l'event_id '{event_id}' (titre : '{event_title}') "
        f"au {new_date}, nouvelle heure de début : {new_start}, nouvelle heure de fin : {new_end}. "
        f"Utilise directement update_meeting avec cet event_id sans faire de recherche."
    )
    try:
        response = await send_task("calendar", message)
        return json.dumps({"success": True, "response": response}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Impossible de replanifier '{event_title}' : {str(e)}"}, ensure_ascii=False)


@tool
async def notify_manager(user_id: int, message: str) -> str:
    """Notifie le manager de l'employé via Slack."""
    denied = await _check_rbac("notify_manager")
    if denied: return denied
    return json.dumps({
        "success": True,
        "message": f"✅ [MOCK] Notification envoyée au manager : {message}"
    })


@tool
async def check_leave_balance(user_id: int, requested_days: int = 0) -> str:
    """Vérifie le solde de congés disponible d'un employé."""
    denied = await _check_rbac("check_leave_balance")
    if denied: return denied
    result = await rh_tools.check_leave_balance(user_id=user_id, requested_days=requested_days)
    return json.dumps(result, ensure_ascii=False)


# ══════════════════════════════════════════════════════
# LISTE DES OUTILS
# ══════════════════════════════════════════════════════

TOOLS = [
    check_leave_balance,
    create_leave,
    get_my_leaves,
    get_team_availability,
    get_team_stack,
    check_calendar_conflicts,
    reschedule_meeting,
    notify_manager,
]


# ══════════════════════════════════════════════════════
# A2A EXECUTOR avec failover
# ══════════════════════════════════════════════════════

class RHAgentExecutor(AgentExecutor):
    """
    Pont entre le protocole A2A et le ReAct agent RH.
    Failover : si la clé Groq tombe, reconstruit le ReAct agent
    avec la clé suivante et retente.
    """

    def __init__(self) -> None:
        self._build_react_agent()

    def _build_react_agent(self) -> None:
        """Construit le ReAct agent avec la clé Groq active."""
        llm = build_llm(
            model="openai/gpt-oss-120b",
            temperature=0,
            max_tokens=2048,
        )
        self.react_agent = create_react_agent(
            model=llm,
            tools=TOOLS,
            prompt=RH_REACT_PROMPT,
        )

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        global _current_role
        user_input = context.get_user_input()
        _current_role = _extract_role_from_message(user_input)

        print(f"\n{'='*50}")
        print(f"🤖 RHAgent ReAct (Groq 120B) — Message reçu : {user_input[:200]}")
        print(f"🔐 Rôle utilisateur : {_current_role}")
        print(f"{'='*50}")

        # ── Tentative avec failover ────────────────────────
        max_retries = 3
        result = None
        for attempt in range(max_retries):
            try:
                result = await self.react_agent.ainvoke({
                    "messages": [HumanMessage(content=user_input)]
                })
                break

            except Exception as e:
                if _is_quota_error(e):
                    print(f"⚠️ Quota tokens dépassé (RH) : {str(e)[:120]}")
                    response_with_steps = json.dumps({
                        "response": FRIENDLY_QUOTA_MSG,
                        "react_steps": [],
                    }, ensure_ascii=False)
                    message = new_agent_text_message(response_with_steps)
                    await event_queue.enqueue_event(message)
                    return
                elif _is_fallback_error(e) and rotate_llm_key():
                    print(f"⚠️ Clé Groq échouée (tentative {attempt+1}/{max_retries}) → rotation")
                    self._build_react_agent()
                    continue
                else:
                    print(f"❌ Erreur ReAct : {str(e)}")
                    response_with_steps = json.dumps({
                        "response": f"Erreur lors du traitement : {str(e)}",
                        "react_steps": [],
                    }, ensure_ascii=False)
                    message = new_agent_text_message(response_with_steps)
                    await event_queue.enqueue_event(message)
                    return

        if result is None:
            response_with_steps = json.dumps({
                "response": "Toutes les clés API sont temporairement indisponibles. Veuillez réessayer.",
                "react_steps": [],
            }, ensure_ascii=False)
            message = new_agent_text_message(response_with_steps)
            await event_queue.enqueue_event(message)
            return

        # ── Extrait les steps du cycle ReAct ──────────────
        react_steps = []
        tool_calls_map = {}

        for msg in result["messages"]:
            msg_type = type(msg).__name__
            if msg_type == "AIMessage" and msg.tool_calls:
                for tc in msg.tool_calls:
                    step_text = _tool_to_human_text(tc['name'], tc['args'])
                    react_steps.append(step_text)
                    tool_calls_map[tc['id']] = len(react_steps) - 1

            elif msg_type == "ToolMessage":
                obs = _format_observation(msg.content)
                if obs:
                    tool_call_id = getattr(msg, 'tool_call_id', None)
                    if tool_call_id and tool_call_id in tool_calls_map:
                        idx = tool_calls_map[tool_call_id]
                        react_steps[idx] += f"\n   → {obs}"

        # ── Log terminal ──────────────────────────────────
        print(f"\n{'─'*50}")
        print("🧠 CYCLE ReAct :")
        for msg in result["messages"]:
            msg_type = type(msg).__name__
            if msg_type == "HumanMessage":
                print(f"  👤 Human  : {msg.content[:500]}")
            elif msg_type == "AIMessage":
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        print(f"  🔧 Act    : {tc['name']}({tc['args']})")
                else:
                    print(f"  🤖 Answer : {msg.content[:200]}")
            elif msg_type == "ToolMessage":
                print(f"  👁️  Observe: {msg.content[:100]}")
        print(f"{'─'*50}\n")

        final_response = result["messages"][-1].content

        response_with_steps = json.dumps({
            "response": final_response,
            "react_steps": react_steps,
        }, ensure_ascii=False)

        message = new_agent_text_message(response_with_steps)
        await event_queue.enqueue_event(message)

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        pass


# ══════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ══════════════════════════════════════════════════════

def _tool_to_human_text(tool_name: str, args: dict) -> str:
    mapping = {
        "check_leave_balance": "💰 Vérification du solde de congés...",
        "check_calendar_conflicts": (
            f"🔍 Vérification du calendrier du {args.get('start_date')} "
            f"au {args.get('end_date')}..."
        ),
        "create_leave": (
            f"📝 Création du congé du {args.get('start_date')} "
            f"au {args.get('end_date')}..."
        ),
        "notify_manager": "📢 Notification du manager...",
        "get_my_leaves": (
            f"📋 Récupération des congés"
            f"{' en attente' if args.get('status_filter') == 'pending' else ''}..."
        ),
        "get_team_availability": "👥 Vérification de la disponibilité de l'équipe...",
        "get_team_stack": "💼 Récupération des compétences de l'équipe...",
    }
    return mapping.get(tool_name, f"⚙️ {tool_name}...")


def _format_observation(content: str) -> str:
    try:
        data = json.loads(content)
        if data.get("success"):
            if "solde_effectif" in data:
                solde = data['solde_effectif']
                total = data['solde_total']
                pending = data['jours_pending']
                can = data.get('can_create')
                base = f"Solde effectif : {solde} jours ({total} total - {pending} en attente)"
                if can is True:
                    return f"{base} ✅"
                elif can is False:
                    return f"{base} ❌ Solde insuffisant"
                return f"{base} ✅"
            if "conflicts" in data:
                conflicts = data.get("conflicts", [])
                return "Aucun conflit trouvé ✅" if not conflicts else f"{len(conflicts)} conflit(s) ⚠️"
            if "leave_id" in data:
                return f"Congé créé (ID: {data['leave_id']}) ✅"
            if "message" in data:
                return f"{data['message']} ✅"
        elif "error" in data:
            return f"❌ {data['error']}"
    except Exception:
        pass
    return ""