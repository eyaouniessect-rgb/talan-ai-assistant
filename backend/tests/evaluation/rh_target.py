"""
ÉTAPE 2 — Target function : appelle l'agent RH via HTTP A2A (port 8001).

Prérequis : l'agent RH doit tourner.
    python -m agents.rh.server
"""
import os
import json
import asyncio
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from app.a2a.client import send_task_to_url_streaming

AGENT_RH_URL = f"http://{os.getenv('AGENT_HOST', 'localhost')}:{os.getenv('AGENT_RH_PORT', '8001')}"

# Mapping role → user_id réel dans la base
USER_IDS = {
    "consultant": 22,   # Eya ouni
    "rh": 1,            # Ons RH (premier user créé)
}


def _build_enriched_message(message: str, role: str) -> str:
    """
    Reproduit le format que node3 envoie à l'agent RH.
    L'agent extrait le rôle via _extract_role_from_message().
    """
    user_id = USER_IDS.get(role, 22)
    return (
        f"Role utilisateur : {role}\n"
        f"User ID : {user_id}\n"
        f"Date du jour : 2026-05-17\n"
        f"---\n"
        f"{message}"
    )


def _extract_tools_from_response(response_text: str) -> list[str]:
    """
    Détecte les tools appelés à partir des messages humains streamés
    (mapping inverse de utils/streaming.py::rh_tool_to_human_text).

    Note : LangSmith capture aussi les vrais tool_calls via tracing.
    Cette heuristique sert au scoring rapide côté Python.
    """
    # Marqueurs distinctifs (émoji + mots-clés) → nom technique
    HUMAN_MARKERS = [
        ("Vérification du solde de congés",         "check_leave_balance"),
        ("Récupération de vos congés",              "get_my_leaves"),
        ("Création du congé",                       "create_leave"),
        ("Annulation du congé",                     "delete_leave"),
        ("Notification du manager",                 "notify_manager"),
        ("disponibilité de l'équipe «",             "get_team_availability_by_name"),
        ("disponibilité de l'équipe",               "get_team_availability"),
        ("Récupération des compétences",            "get_team_stack"),
        ("Vérification du calendrier",              "check_calendar_conflicts"),
        ("Recherche des demandes de congé",         "get_leaves_by_filter"),
        ("Approbation du congé",                    "approve_leave_request"),
        ("Refus du congé",                          "reject_leave_request"),
        ("Mise à jour du profil",                   "update_employee_info"),
        ("Récupération de tous les congés",         "get_all_leaves"),
        ("Création du compte",                      "create_user_account"),
        ("Désactivation du compte",                 "deactivate_user"),
    ]

    # Fallback : noms techniques bruts dans le texte
    KNOWN_TOOLS = [
        "check_leave_balance", "create_leave", "delete_leave", "get_my_leaves",
        "approve_leave_request", "reject_leave_request", "get_leaves_by_filter",
        "get_my_profile", "update_employee_info",
        "get_team_availability", "get_team_availability_by_name", "get_team_stack",
        "check_calendar_conflicts", "reschedule_meeting", "remove_meeting_attendee",
        "notify_manager", "send_email",
    ]

    found: list[str] = []
    seen: set[str] = set()

    # 1) Marqueurs humains (priorité)
    for marker, tool_name in HUMAN_MARKERS:
        if marker in response_text and tool_name not in seen:
            found.append(tool_name)
            seen.add(tool_name)

    # 2) Noms techniques au cas où
    for tool in KNOWN_TOOLS:
        if tool in response_text and tool not in seen:
            found.append(tool)
            seen.add(tool)

    return found


async def _call_agent(message: str, role: str) -> dict[str, Any]:
    """
    Appelle l'agent RH en mode streaming pour capter la réponse finale,
    qu'elle arrive via Message, task.status.message OU task.artifacts.
    """
    enriched = _build_enriched_message(message, role)
    final_text = ""
    intermediate_texts: list[str] = []

    try:
        async for event_type, text in send_task_to_url_streaming(AGENT_RH_URL, enriched):
            if event_type == "done":
                final_text = text
            elif event_type in ("message", "status", "artifact"):
                if text:
                    intermediate_texts.append(text)
    except Exception as e:
        return {"response": f"[ERROR] {e}", "tools_called": [], "error": str(e)}

    # Concatène tout ce qui a transité pour ne rien perdre
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


def run_rh_agent(inputs: dict) -> dict:
    """
    Fonction synchrone appelée par LangSmith evaluate().
    Retourne {response, tools_called} qui sera passé aux evaluators.
    """
    message = inputs["message"]
    role = inputs.get("role", "consultant")
    return asyncio.run(_call_agent(message, role))


if __name__ == "__main__":
    # Test rapide
    result = run_rh_agent({
        "message": "Combien de jours de congé me reste-t-il ?",
        "role": "consultant",
    })
    print("Response:", result["response"][:200])
    print("Tools détectés:", result["tools_called"])
