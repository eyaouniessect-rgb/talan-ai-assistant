"""
ÉTAPE 2 — Target function : appelle l'agent Calendar via HTTP A2A (port 8002).

Prérequis :
  1. Agent Calendar démarré : python -m agents.calendar.server
  2. MCP Google Calendar démarré (http://127.0.0.1:3000/mcp)
  3. Token OAuth valide pour l'utilisateur Eya ouni
"""
import os
import json
import asyncio
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from app.a2a.client import send_task_to_url_streaming

AGENT_CALENDAR_URL = f"http://{os.getenv('AGENT_HOST', 'localhost')}:{os.getenv('AGENT_CALENDAR_PORT', '8002')}"

# Mapping role → user_id réel dans la base
USER_IDS = {
    "consultant": 22,   # Eya ouni
    "rh": 1,            # Ons RH
}


def _build_enriched_message(message: str, role: str) -> str:
    """
    Reproduit le format que node3 envoie à l'agent Calendar.
    L'agent extrait role + user_id via _extract_*_from_message().
    """
    user_id = USER_IDS.get(role, 22)
    return (
        f"Role utilisateur : {role}\n"
        f"User ID : {user_id}\n"
        f"Date du jour : 2026-05-18\n"
        f"---\n"
        f"{message}"
    )


def _extract_tools_from_response(text: str) -> list[str]:
    """
    Détecte les tools appelés via les messages humains streamés
    (mapping inverse de utils/streaming.py::calendar_tool_to_human_text).
    """
    # Marqueurs distinctifs (mots-clés uniques) → nom technique
    HUMAN_MARKERS = [
        ("Consultation des événements",            "get_calendar_events"),
        ("Vérification des disponibilités",        "check_calendar_conflicts"),
        ("Recherche d'événements",                 "search_meetings"),
        ("Création de l'événement",                "create_meeting"),
        ("Modification de l'événement",            "update_meeting"),
        ("Suppression de l'événement",             "delete_meeting"),
        ("Recherche de l'email de",                "lookup_user_by_name"),
        ("get_my_manager",                          "get_my_manager"),
        ("get_my_team",                             "get_my_team"),
    ]

    # Fallback : noms techniques bruts
    KNOWN_TOOLS = [
        "check_calendar_conflicts", "get_calendar_events", "create_meeting",
        "update_meeting", "delete_meeting", "search_meetings",
        "lookup_user_by_name", "get_my_manager", "get_my_team",
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
    Appelle l'agent Calendar en streaming et collecte la réponse finale.
    """
    enriched = _build_enriched_message(message, role)
    final_text = ""
    intermediate_texts: list[str] = []

    try:
        async for event_type, text in send_task_to_url_streaming(AGENT_CALENDAR_URL, enriched):
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


def run_calendar_agent(inputs: dict) -> dict:
    """
    Fonction synchrone appelée par LangSmith evaluate().
    """
    message = inputs["message"]
    role = inputs.get("role", "consultant")
    return asyncio.run(_call_agent(message, role))


if __name__ == "__main__":
    # Test rapide
    result = run_calendar_agent({
        "message": "Quelles sont mes réunions cette semaine ?",
        "role": "consultant",
    })
    print("Response:", result["response"][:300])
    print("Tools détectés:", result["tools_called"])
