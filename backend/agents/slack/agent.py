# agents/slack/agent.py
# ═══════════════════════════════════════════════════════════
# Agent Slack — ReAct (LangGraph) avec failover clés Groq
# Outils : send_message, read_channel, search_messages,
#           list_channels, get_thread_replies, get_user
# ═══════════════════════════════════════════════════════════

from dotenv import load_dotenv
import asyncio
import json
from typing import Optional

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.slack.prompts import SLACK_REACT_PROMPT
from agents.slack import tools as slack_tools
from app.core.groq_client import (
    build_llm, build_llm_groq_fallback, rotate_llm_key,
    _is_fallback_error, _is_tpm_error, _is_context_error,
    FRIENDLY_QUOTA_MSG, FRIENDLY_CONTEXT_MSG,
)
from utils.streaming import enqueue_final as _enqueue_final_shared, enqueue_working
from langsmith import trace

load_dotenv()


async def _enqueue_final(event_queue: EventQueue, text: str, task_id: str, context_id: str, status_emitted: int = 0) -> None:
    await _enqueue_final_shared(event_queue, text, task_id, context_id)


# ══════════════════════════════════════════════════════
# OUTILS LANGCHAIN
# ══════════════════════════════════════════════════════

@tool
async def send_slack_message(channel: str, text: str, thread_ts: Optional[str] = None) -> str:
    """
    Envoie un message dans un channel Slack ou en réponse dans un thread.
    channel  : nom du channel (#general, #dev-team) ou ID (C012AB3CD)
    text     : contenu du message à envoyer
    thread_ts: (optionnel) timestamp du message parent pour répondre dans un thread
    """
    try:
        if thread_ts:
            result = await slack_tools.reply_to_thread(channel=channel, thread_ts=thread_ts, text=text)
        else:
            result = await slack_tools.send_message(channel=channel, text=text)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@tool
async def read_slack_channel(channel: str, limit: int = 20) -> str:
    """
    Lit les N derniers messages d'un channel Slack.
    channel : nom du channel (#general) ou son ID
    limit   : nombre de messages à récupérer (défaut : 20, max : 100)
    """
    try:
        result = await slack_tools.read_channel(channel=channel, limit=limit)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@tool
async def search_slack_messages(query: str, count: int = 10) -> str:
    """
    Recherche des messages dans Slack.
    query : mot-clé ou expression de recherche.
            Filtres supportés : in:#channel, from:@user, after:YYYY-MM-DD
    count : nombre de résultats (défaut : 10)
    """
    try:
        result = await slack_tools.search_messages(query=query, count=count)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@tool
async def list_slack_channels() -> str:
    """
    Liste tous les channels Slack disponibles avec leurs IDs.
    Utiliser pour trouver l'ID d'un channel à partir de son nom.
    """
    try:
        result = await slack_tools.get_channel_list()
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@tool
async def get_thread_replies(channel: str, thread_ts: str) -> str:
    """
    Récupère toutes les réponses d'un thread Slack.
    channel   : ID du channel contenant le thread
    thread_ts : timestamp du message parent (champ ts dans les messages)
    """
    try:
        result = await slack_tools.get_thread_replies(channel=channel, thread_ts=thread_ts)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@tool
async def get_slack_user(user_id: str) -> str:
    """
    Retourne le profil d'un utilisateur Slack (nom, email, statut).
    user_id : ID Slack de l'utilisateur (format U012AB3CD)
    """
    try:
        result = await slack_tools.get_user_profile(user_id=user_id)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@tool
async def find_slack_user(name: str) -> str:
    """
    Cherche un utilisateur Slack par son nom (prénom, nom complet ou email).
    Retourne l'ID Slack (format U...) nécessaire pour envoyer un DM.
    TOUJOURS utiliser cet outil avant d'envoyer un DM à une personne nommée.
    Exemples : "Chaima Hermi", "chaima", "Ahmed"
    """
    try:
        result = await slack_tools.find_user_by_name(name=name)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


TOOLS = [
    send_slack_message,
    read_slack_channel,
    search_slack_messages,
    list_slack_channels,
    get_thread_replies,
    get_slack_user,
    find_slack_user,
]


# ══════════════════════════════════════════════════════
# HELPER — texte lisible pour les étapes intermédiaires
# ══════════════════════════════════════════════════════

def _tool_to_human_text(tool_name: str, args: dict) -> str:
    mapping = {
        "send_slack_message":   lambda a: f"Envoi d'un message dans **{a.get('channel', '?')}**...",
        "read_slack_channel":   lambda a: f"Lecture et résolution des auteurs de **{a.get('channel', '?')}**...",
        "search_slack_messages":lambda a: f"Recherche Slack : *{a.get('query', '?')}*...",
        "list_slack_channels":  lambda a: "Récupération de la liste des channels...",
        "get_thread_replies":   lambda a: f"Récupération du thread dans **{a.get('channel', '?')}**...",
        "get_slack_user":       lambda a: f"Récupération du profil utilisateur `{a.get('user_id', '?')}`...",
        "find_slack_user":      lambda a: f"Recherche de l'utilisateur **{a.get('name', '?')}** dans Slack...",
    }
    fn = mapping.get(tool_name)
    return fn(args) if fn else f"Exécution de {tool_name}..."


# ══════════════════════════════════════════════════════
# A2A EXECUTOR avec failover Groq
# ══════════════════════════════════════════════════════

class SlackAgentExecutor(AgentExecutor):
    """
    Pont entre le protocole A2A et le ReAct agent Slack.
    Failover : si la clé Groq tombe, reconstruit le ReAct agent
    avec la clé suivante et retente.
    """

    def __init__(self) -> None:
        self._build_react_agent()

    def _build_react_agent(self, use_groq_fallback: bool = False) -> None:
        llm = (build_llm_groq_fallback if use_groq_fallback else build_llm)(
            model="openai/gpt-oss-120b",
            temperature=0,
            max_tokens=2500,
        )
        self.react_agent = create_react_agent(
            model=llm,
            tools=TOOLS,
            prompt=SLACK_REACT_PROMPT,
        )

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        user_input = context.get_user_input()
        task_id    = context.task_id or "task"
        context_id = context.context_id or "ctx"

        print(f"\n{'='*50}")
        print(f"🤖 SlackAgent ReAct — Message reçu : {user_input[:200]}")
        print(f"{'='*50}")

        max_retries = 3

        with trace(
            name="slack_agent.execute",
            run_type="chain",
            inputs={"user_input": user_input[:1000]},
            tags=["agent", "slack"],
        ) as ls_run:

            for attempt in range(max_retries):
                result_messages = None
                status_events_emitted = 0

                try:
                    async for event in self.react_agent.astream_events(
                        {"messages": [HumanMessage(content=user_input)]},
                        version="v2",
                        config={"recursion_limit": 10},
                    ):
                        etype = event["event"]

                        if etype == "on_tool_start":
                            tool_name = event["name"]
                            tool_args = event["data"].get("input") or {}
                            if not isinstance(tool_args, dict):
                                tool_args = {}
                            step_text = _tool_to_human_text(tool_name, tool_args)
                            print(f"  🔧 [STREAM] Tool start: {tool_name}({tool_args})")
                            await enqueue_working(event_queue, step_text, task_id, context_id)
                            status_events_emitted += 1

                        elif etype == "on_chain_end":
                            output = event["data"].get("output", {})
                            if isinstance(output, dict) and "messages" in output:
                                result_messages = output["messages"]

                    break

                except Exception as e:
                    if _is_context_error(e):
                        print(f"⚠️ Contexte trop long (Slack) : {str(e)[:120]}")
                        final_response = FRIENDLY_CONTEXT_MSG
                        ls_run.end(outputs={"response": final_response, "error": "context"})
                        await _enqueue_final(event_queue, json.dumps({"response": final_response, "react_steps": []}, ensure_ascii=False), task_id, context_id, status_events_emitted)
                        return
                    elif _is_tpm_error(e) and rotate_llm_key():
                        print(f"⚠️ TPM dépassé (Slack tentative {attempt+1}/{max_retries}), rotation clé Groq")
                        self._build_react_agent(use_groq_fallback=True)
                        await asyncio.sleep(3)
                        continue
                    elif _is_tpm_error(e):
                        print(f"⚠️ TPM dépassé (Slack) — toutes les clés épuisées")
                        final_response = FRIENDLY_QUOTA_MSG
                        ls_run.end(outputs={"response": final_response, "error": "quota"})
                        await _enqueue_final(event_queue, json.dumps({"response": final_response, "react_steps": []}, ensure_ascii=False), task_id, context_id, status_events_emitted)
                        return
                    elif _is_fallback_error(e) and rotate_llm_key() and status_events_emitted == 0:
                        print(f"⚠️ [Groq Slack] Clé invalide (tentative {attempt+1}/{max_retries}) → rotation")
                        self._build_react_agent(use_groq_fallback=True)
                        continue
                    else:
                        print(f"❌ Erreur ReAct Slack : {str(e)}")
                        final_response = "Une erreur inattendue s'est produite. Veuillez réessayer."
                        ls_run.end(outputs={"response": final_response, "error": str(e)})
                        await _enqueue_final(event_queue, json.dumps({"response": final_response, "react_steps": []}, ensure_ascii=False), task_id, context_id, status_events_emitted)
                        return
            else:
                final_response = "Toutes les clés API sont temporairement indisponibles. Veuillez réessayer."
                ls_run.end(outputs={"response": final_response, "error": "all_keys_exhausted"})
                await _enqueue_final(event_queue, json.dumps({"response": final_response, "react_steps": []}, ensure_ascii=False), task_id, context_id, status_events_emitted)
                return

            # ── Extraction de la réponse finale ───────────────
            react_steps = []
            tool_calls_map = {}
            final_response = "L'agent Slack n'a pas retourné de réponse."

            if result_messages:
                print(f"\n{'─'*50}")
                print("🧠 CYCLE ReAct — SlackAgent :")

                for msg in result_messages:
                    msg_type = type(msg).__name__
                    if msg_type == "AIMessage":
                        if msg.content:
                            print(f"  🤔 Think  : {msg.content[:300]}")
                        if msg.tool_calls:
                            for tc in msg.tool_calls:
                                step_text = _tool_to_human_text(tc['name'], tc['args'])
                                react_steps.append(step_text)
                                tool_calls_map[tc['id']] = len(react_steps) - 1
                                print(f"  🔧 Act    : {tc['name']}({tc['args']})")
                    elif msg_type == "ToolMessage":
                        print(f"  👁️  Observe: {msg.content[:200]}")
                    elif msg_type == "HumanMessage":
                        print(f"  👤 Human  : {msg.content[:200]}")

                print(f"{'─'*50}\n")
                final_response = result_messages[-1].content

            ls_run.end(outputs={
                "response": final_response[:500] if final_response else "",
                "react_steps": react_steps,
            })

            await _enqueue_final(
                event_queue,
                json.dumps({"response": final_response, "react_steps": react_steps}, ensure_ascii=False),
                task_id,
                context_id,
                status_events_emitted,
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass
