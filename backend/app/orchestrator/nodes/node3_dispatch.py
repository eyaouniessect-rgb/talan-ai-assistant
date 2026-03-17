# Node 3 — Dispatch via le protocole A2A.
# Selon l'agent cible détecté en Node 1, envoie une requête HTTP A2A
# au bon serveur d'agent (agent_rh:8001, agent_crm:8002, etc.)
# Gère aussi :
#   - L'exécution parallèle si plusieurs agents sont indépendants
#   - Le timeout et la gestion d'erreur par agent
#   - Le routing vers le Module RAG si l'intention est "search_docs"

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from app.orchestrator.state import AssistantState
from app.a2a.client import send_task
from dotenv import load_dotenv
import os

load_dotenv()

MAX_HISTORY = 6

# LLM pour les réponses de conversation générale
llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
    temperature=0.7,
)

CHAT_PROMPT = """
Tu es Talan Assistant, un assistant d'entreprise intelligent pour Talan Tunisie.
Tu aides les employés avec leurs tâches quotidiennes :
- Congés et ressources humaines (Agent RH)
- Projets et clients (Agent CRM)
- Tickets Jira (Agent Jira)
- Messages Slack (Agent Slack)
- Calendrier Google (Agent Calendar)
- Recherche dans les documents internes (RAG)

Réponds toujours en français, de façon concise et professionnelle.
Si l'utilisateur salue, salue-le chaleureusement et présente brièvement tes capacités.
Si l'utilisateur pose une question sur la conversation précédente, utilise le contexte fourni.
Ne révèle jamais les détails techniques de ton architecture.
"""


async def node3_dispatch(state: AssistantState) -> AssistantState:
    """
    Node 3 — Dispatch vers le bon agent ou répond directement.

    Cas 1 : intent = "chat"    → LLM répond avec historique (bonjour, questions...)
    Cas 2 : intent = "unknown" → message d'erreur
    Cas 3 : intent = action    → dispatch vers l'agent A2A correspondant
    """
    intent       = state["intent"]
    target_agent = state["target_agent"]
    entities     = state["entities"]
    user_id      = state["user_id"]

    # ── Cas 1 : conversation générale avec historique ──────
    if intent == "chat" or (target_agent == "none" and intent != "unknown"):
        last_message = state["messages"][-1].content

        # Trim — garde les N derniers messages pour le contexte
        all_messages = state["messages"]
        trimmed = all_messages[-MAX_HISTORY:] if len(all_messages) > MAX_HISTORY else all_messages

        # Construit l'historique pour Gemini
        history_messages = []
        for msg in trimmed[:-1]:  # tous sauf le dernier
            if msg.type == "human":
                history_messages.append(HumanMessage(content=msg.content))
            else:
                history_messages.append(AIMessage(content=msg.content))

        # Appelle Gemini avec tout le contexte
        response = await llm.ainvoke([
            SystemMessage(content=CHAT_PROMPT),
            *history_messages,
            HumanMessage(content=last_message),
        ])
        return {**state, "final_response": response.content}

    # ── Cas 2 : intent inconnu ────────────────────────────
    if intent == "unknown":
        return {
            **state,
            "final_response": (
                "Je n'ai pas compris votre demande. "
                "Voici ce que je peux faire :\n"
                "- Créer ou consulter des congés\n"
                "- Voir vos projets et clients\n"
                "- Gérer vos tickets Jira\n"
                "- Envoyer des messages Slack\n"
                "- Gérer votre calendrier\n"
                "Pouvez-vous reformuler ?"
            )
        }

    # ── Cas 3 : dispatch vers l'agent A2A ─────────────────
    # Envoie le message original + contexte enrichi
    original_message = state["messages"][-1].content
    message =(f"Original message: {original_message}. "
             f"Intent: {intent}. "
             f"Entities: {entities}. "
             f"User ID: {user_id}.")


    

    try:
        response = await send_task(target_agent, message)
    except Exception as e:
        response = (
            f"L'agent {target_agent} est temporairement indisponible. "
            f"Erreur : {str(e)}"
        )

    return {**state, "final_response": response}