# Node 3 — Dispatch via le protocole A2A.
# Selon l'agent cible détecté en Node 1, envoie une requête HTTP A2A
# au bon serveur d'agent (agent_rh:8001, agent_crm:8002, etc.)

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from app.orchestrator.state import AssistantState
from app.a2a.client import send_task
from dotenv import load_dotenv
import os
import json

load_dotenv()

MAX_HISTORY = 6

llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    temperature=0.7,
)

CHAT_PROMPT = """
Tu es Talan Assistant, un assistant d'entreprise intelligent pour Talan Tunisie.

RÈGLE CRITIQUE :
Quand l'utilisateur dit "merci", "d'accord", "ok" ou exprime de la gratitude,
réponds SIMPLEMENT et chaleureusement. 
Ne liste JAMAIS des actions ou des données sauf si l'utilisateur le demande explicitement.
Exemples de bonnes réponses :
- "De rien ! N'hésitez pas si vous avez d'autres questions."
- "Avec plaisir ! Je suis là si vous avez besoin."
- "Bonne journée !"

RÈGLE SUR LES DONNÉES :
Ne déduis JAMAIS qu'une action a été effectuée à partir des messages de l'utilisateur.
Utilise UNIQUEMENT les confirmations explicites des réponses de l'Assistant.

Tu aides les employés avec :
- Congés et ressources humaines (Agent RH)
- Projets et clients (Agent CRM)
- Tickets Jira (Agent Jira)
- Messages Slack (Agent Slack)
- Calendrier Google (Agent Calendar)
- Recherche dans les documents internes (RAG)

Réponds toujours en français, de façon concise et professionnelle.
Ne révèle jamais les détails techniques de ton architecture.
"""

def _extract_clean_text(content: str) -> str:
    """
    Extrait le texte propre d'une réponse.
    Si c'est un JSON (réponse Agent ReAct) → retourne juste le champ 'response'.
    Sinon → retourne le contenu tel quel.
    """
    try:
        parsed = json.loads(content)
        return parsed.get("response", content)
    except (json.JSONDecodeError, TypeError):
        return content


async def node3_dispatch(state: AssistantState) -> AssistantState:
    """
    Node 3 — Dispatch vers le bon agent ou répond directement.

    Cas 1 : intent = "chat"    → LLM répond avec historique propre
    Cas 2 : intent = "unknown" → message d'erreur
    Cas 3 : intent = action    → dispatch vers l'agent A2A avec historique propre
    """
    intent       = state["intent"]
    target_agent = state["target_agent"]
    entities     = state["entities"]
    user_id      = state["user_id"]

    # ── Trim commun ────────────────────────────────────────
    all_messages = state["messages"]
    trimmed = all_messages[-MAX_HISTORY:] if len(all_messages) > MAX_HISTORY else all_messages

    # ── Cas 1 : conversation générale avec historique ──────
    if intent == "chat" or (target_agent == "none" and intent != "unknown"):
        last_message = state["messages"][-1].content

        history_messages = []
        for msg in trimmed[:-1]:
            if msg.type == "human":
                history_messages.append(HumanMessage(content=msg.content))
            else:
                # ← parse le JSON pour avoir le texte propre
                clean = _extract_clean_text(msg.content)
                history_messages.append(AIMessage(content=clean))

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

    # ── Cas 3 : dispatch vers l'agent A2A avec historique ──
    original_message = state["messages"][-1].content

    # ← Construit l'historique propre (sans JSON brut)
    history = ""
    for msg in trimmed[:-1]:
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        clean = _extract_clean_text(msg.content)  # ← texte propre
        history += f"{role}: {clean}\n"

    message = (
        f"Historique récent de la conversation :\n{history}\n"
        f"---\n"
        f"Message utilisateur : {original_message}\n"
        f"Intent : {intent}\n"
        f"Entités : {entities}\n"
        f"User ID : {user_id}"
    )

    try:
        response = await send_task(target_agent, message)
    except Exception as e:
        response = (
            f"L'agent {target_agent} est temporairement indisponible. "
            f"Erreur : {str(e)}"
        )

    return {**state, "final_response": response}