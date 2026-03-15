# Node 3 — Dispatch via le protocole A2A.
# Selon l'agent cible détecté en Node 1, envoie une requête HTTP A2A
# au bon serveur d'agent (agent_rh:8001, agent_crm:8002, etc.)
# Gère aussi :
#   - L'exécution parallèle si plusieurs agents sont indépendants
#   - Le timeout et la gestion d'erreur par agent
#   - Le routing vers le Module RAG si l'intention est "search_docs"
# app/orchestrator/nodes/node3_dispatch.py
from app.orchestrator.state import AssistantState
from app.a2a.client import send_task


async def node3_dispatch(state: AssistantState) -> AssistantState:
    """
    Node 3 — Dispatch vers le vrai agent A2A.
    """
    intent       = state["intent"]
    target_agent = state["target_agent"]
    entities     = state["entities"]
    user_id      = state["user_id"]

    # Construit le message pour l'agent
    message = f"Intent: {intent}. Entities: {entities}. User ID: {user_id}"

    try:
        if target_agent == "none" or intent == "unknown":
            response = "Je n'ai pas compris votre demande. Pouvez-vous reformuler ?"
        else:
            response = await send_task(target_agent, message)
    except Exception as e:
        response = f"Erreur lors de la communication avec l'agent {target_agent} : {str(e)}"

    return {**state, "final_response": response}


