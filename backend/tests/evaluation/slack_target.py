"""
ÉTAPE 2 — Target function : appelle l'agent Slack via HTTP A2A (port 8005).

Prérequis :
  1. Agent Slack démarré : python -m agents.slack.server
  2. SLACK_BOT_TOKEN ou SLACK_USER_TOKEN configuré dans .env
"""
import os
import json
import asyncio
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from app.a2a.client import send_task_to_url_streaming

AGENT_SLACK_URL = f"http://{os.getenv('AGENT_HOST', 'localhost')}:{os.getenv('AGENT_SLACK_PORT', '8005')}"

# Mapping role → user_id réel dans la base
USER_IDS = {
    "consultant": 22,   # Eya ouni
    "rh": 1,            # Ons RH
}

# Mapping role → nom/email pour la signature des messages
USER_PROFILES = {
    "consultant": ("Eya Ouni", "eyaouniessect@gmail.com"),
    "rh": ("Ons RH", "ons.rh.talan@gmail.com"),
}


def _build_enriched_message(message: str, role: str) -> str:
    """
    Reproduit le format que node3 envoie à l'agent Slack.
    L'agent Slack a besoin de :
      - Date du jour
      - Nom de l'utilisateur connecté (pour la signature)
      - Email
      - INSTRUCTION À EXÉCUTER
      - Role + User ID
    """
    user_id = USER_IDS.get(role, 22)
    user_name, user_email = USER_PROFILES.get(role, ("Eya Ouni", "eyaouniessect@gmail.com"))
    return (
        f"Date du jour : 2026-05-22\n"
        f"---\n"
        f"Nom de l'utilisateur connecté : {user_name}\n"
        f"Email : {user_email}\n"
        f"INSTRUCTION À EXÉCUTER :\n{message}\n"
        f"---\n"
        f"Role utilisateur : {role}\n"
        f"User ID : {user_id}\n"
    )


def _extract_tools_from_response(text: str) -> list[str]:
    """
    Détecte les tools appelés via les messages humains streamés
    (mapping inverse de slack/agent.py::_tool_to_human_text).
    """
    # Marqueurs distinctifs (mots-clés uniques) → nom technique
    HUMAN_MARKERS = [
        ("Envoi d'un message dans",                "send_slack_message"),
        ("Lecture et résolution des auteurs",      "read_slack_channel"),
        ("Recherche Slack",                        "search_slack_messages"),
        ("Récupération de la liste des channels",  "list_slack_channels"),
        ("Récupération du thread dans",            "get_thread_replies"),
        ("Récupération du profil utilisateur",     "get_slack_user"),
        ("Recherche de l'utilisateur",             "find_slack_user"),
        ("Ajout de la réaction",                   "add_slack_reaction"),
        ("Retrait de la réaction",                 "remove_slack_reaction"),
    ]

    # Fallback : noms techniques bruts
    KNOWN_TOOLS = [
        "send_slack_message", "read_slack_channel", "search_slack_messages",
        "list_slack_channels", "get_thread_replies", "get_slack_user",
        "find_slack_user", "add_slack_reaction", "remove_slack_reaction",
    ]

    found: list[str] = []
    seen: set[str] = set()

    # 1) Marqueurs humains
    for marker, tool_name in HUMAN_MARKERS:
        if marker in text and tool_name not in seen:
            found.append(tool_name)
            seen.add(tool_name)

    # 2) Noms techniques bruts
    for tool in KNOWN_TOOLS:
        if tool in text and tool not in seen:
            found.append(tool)
            seen.add(tool)

    return found


async def _call_agent(message: str, role: str) -> dict[str, Any]:
    """
    Appelle l'agent Slack en streaming et collecte la réponse finale.
    """
    enriched = _build_enriched_message(message, role)
    final_text = ""
    intermediate_texts: list[str] = []

    try:
        async for event_type, text in send_task_to_url_streaming(AGENT_SLACK_URL, enriched):
            if event_type == "done":
                final_text = text
            elif event_type in ("message", "status", "artifact"):
                if text:
                    intermediate_texts.append(text)
    except Exception as e:
        return {"response": f"[ERROR] {e}", "tools_called": [], "error": str(e)}

    response = final_text or (intermediate_texts[-1] if intermediate_texts else "")

    # Le "done" event retourne parfois un JSON brut avec needs_input:true — extraire le texte pur
    try:
        parsed = json.loads(response)
        if isinstance(parsed, dict):
            response = parsed.get("response") or parsed.get("text") or parsed.get("content") or response
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    full_trace = "\n".join(intermediate_texts) + "\n" + response

    return {
        "response": response or "L'agent n'a pas retourné de réponse.",
        "tools_called": _extract_tools_from_response(full_trace),
    }


def run_slack_agent(inputs: dict) -> dict:
    """
    Fonction synchrone appelée par LangSmith evaluate().
    """
    message = inputs["message"]
    role = inputs.get("role", "consultant")
    return asyncio.run(_call_agent(message, role))


if __name__ == "__main__":
    # Test rapide
    result = run_slack_agent({
        "message": "Quels sont les channels Slack disponibles ?",
        "role": "consultant",
    })
    print("Response:", result["response"][:300])
    print("Tools détectés:", result["tools_called"])
