# agents/rh/agent.py
# ═══════════════════════════════════════════════════════════
# MIGRATION : ChatOllama (qwen3:4b local) → Groq GPT-OSS 120B
# Modèle puissant pour le ReAct agent (raisonnement + tool calling)
# ═══════════════════════════════════════════════════════════
from dotenv import load_dotenv
import os
import json

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from agents.rh.prompts import RH_REACT_PROMPT
from agents.rh import tools as rh_tools

load_dotenv()


# ══════════════════════════════════════════════════════
# OUTILS LANGCHAIN — utilisés par le ReAct agent
# ══════════════════════════════════════════════════════

@tool
async def create_leave(user_id: int, start_date: str, end_date: str) -> str:
    """
    Crée une demande de congé pour un employé.
    Vérifie automatiquement les chevauchements.
    Paramètres: user_id (int), start_date (YYYY-MM-DD), end_date (YYYY-MM-DD)
    """
    result = await rh_tools.create_leave(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_my_leaves(user_id: int, status_filter: str = None) -> str:
    """
    Retourne les congés d'un employé.
    status_filter optionnel: 'pending' | 'approved' | 'rejected' | None (tous)
    """
    result = await rh_tools.get_my_leaves(
        user_id=user_id,
        status_filter=status_filter,
    )
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_team_availability(user_id: int) -> str:
    """
    Retourne la disponibilité de l'équipe de l'employé.
    """
    result = await rh_tools.get_team_availability(user_id=user_id)
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_team_stack(user_id: int) -> str:
    """
    Retourne les compétences techniques de l'équipe.
    """
    result = await rh_tools.get_team_stack(user_id=user_id)
    return json.dumps(result, ensure_ascii=False)


@tool
async def check_calendar_conflicts(user_id: int, start_date: str, end_date: str) -> str:
    """
    Vérifie les conflits dans Google Calendar pour la période donnée.
    Appelle l'Agent Calendar via A2A.
    """
    return json.dumps({
        "success": True,
        "conflicts": [],
        "message": f"Aucun conflit détecté du {start_date} au {end_date}."
    })


@tool
async def notify_manager(user_id: int, message: str) -> str:
    """
    Notifie le manager de l'employé via Slack.
    Appelle l'Agent Slack via A2A.
    """
    return json.dumps({
        "success": True,
        "message": f"✅ [MOCK] Notification envoyée au manager : {message}"
    })


@tool
async def check_leave_balance(user_id: int, requested_days: int = 0) -> str:
    """
    Vérifie le solde de congés disponible d'un employé.
    requested_days: nombre de jours demandés (0 = juste consulter le solde)
    Retourne: solde_total, jours_pending, solde_effectif, can_create
    """
    result = await rh_tools.check_leave_balance(
        user_id=user_id,
        requested_days=requested_days
    )
    return json.dumps(result, ensure_ascii=False)


# ══════════════════════════════════════════════════════
# REACT AGENT RH
# ══════════════════════════════════════════════════════

TOOLS = [
    check_leave_balance,
    create_leave,
    get_my_leaves,
    get_team_availability,
    get_team_stack,
    check_calendar_conflicts,
    notify_manager,
]


# ══════════════════════════════════════════════════════
# A2A EXECUTOR — garde la structure A2A officielle
# ══════════════════════════════════════════════════════
class RHAgentExecutor(AgentExecutor):
    """
    Pont entre le protocole A2A et le ReAct agent RH.
    - Structure A2A : conforme à la doc officielle
    - Logique interne : ReAct agent LangGraph
    - LLM : Groq GPT-OSS 120B (raisonnement complexe + tool calling)
    """

    def __init__(self) -> None:
        # ── Groq GPT-OSS 120B — modèle puissant pour ReAct ──
        llm = ChatOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
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
        user_input = context.get_user_input()

        print(f"\n{'='*50}")
        print(f"🤖 RHAgent ReAct (Groq 120B) — Message reçu : {user_input}")
        print(f"{'='*50}")

        try:
            result = await self.react_agent.ainvoke({
                "messages": [HumanMessage(content=user_input)]
            })

            # ── Extrait les steps du cycle ReAct ──────────
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

            # ── Log terminal ───────────────────────────────
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

        except Exception as e:
            print(f"❌ Erreur ReAct : {str(e)}")
            response_with_steps = json.dumps({
                "response": f"Erreur lors du traitement : {str(e)}",
                "react_steps": [],
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