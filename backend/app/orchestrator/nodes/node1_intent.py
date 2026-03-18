# Node 1 — Détection d'intention.
# Appelle le LLM avec le message utilisateur.
# Extrait :
#   - L'intention (create_leave, get_projects, get_tickets, search_docs, etc.)
#   - L'agent cible (agent_rh, agent_crm, agent_jira, agent_slack, agent_calendar, rag)
#   - Les entités nommées (dates, IDs de tickets, noms de projets)
# Charge aussi l'historique depuis PostgreSQL (long-term memory via Checkpointer).
# app/orchestrator/nodes/node1_intent.py
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from app.orchestrator.state import AssistantState
from dotenv import load_dotenv
import os
import json

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
    temperature=0,
)

# ── Nombre de messages à garder dans le contexte ──────────
MAX_HISTORY_MESSAGES = 6  # 3 échanges (user + assistant)

INTENT_PROMPT = """
Tu es un analyseur d'intention pour un assistant d'entreprise.
Analyse le message utilisateur et retourne UNIQUEMENT un JSON valide.

Intentions possibles :
- create_leave        → agent: rh
- check_leave_balance     → agent: rh
- get_my_leaves       → agent: rh
- get_team_availability → agent: rh
- get_team_stack      → agent: rh
- get_my_projects     → agent: crm
- get_all_projects    → agent: crm
- generate_report     → agent: crm
- get_tickets         → agent: jira
- create_ticket       → agent: jira
- update_ticket       → agent: jira
- send_message        → agent: slack
- get_calendar        → agent: calendar
- create_event        → agent: calendar
- search_docs         → agent: rag
- chat                → agent: none  (salutation, question générale)

Format de réponse OBLIGATOIRE (JSON pur, sans markdown) :
{
  "intent": "nom_de_lintention",
  "target_agent": "nom_de_lagent",
  "entities": {}
}

Exemples d'entités :
- create_leave : {"start_date": "2025-03-15", "end_date": "2025-03-21"}
- create_ticket : {"title": "Bug login", "priority": "High"}

IMPORTANT : Si le message fait référence à une conversation précédente
(ex: "du 15 au 21", "annule ça", "oui confirme"), utilise le contexte
de l'historique pour comprendre l'intention complète.

Si aucune intention ne correspond :
{"intent": "unknown", "target_agent": "none", "entities": {}}
"""

async def node1_detect_intent(state: AssistantState) -> AssistantState:
    """
    Node 1 — Détecte l'intention avec contexte des messages précédents.
    Utilise les MAX_HISTORY_MESSAGES derniers messages (trim).
    """

    # ── 1. Trim — garde seulement les N derniers messages ──
    all_messages = state["messages"]
    trimmed = all_messages[-MAX_HISTORY_MESSAGES:] if len(all_messages) > MAX_HISTORY_MESSAGES else all_messages

    # ── 2. Construit l'historique pour le prompt ───────────
    history = ""
    for msg in trimmed[:-1]:  # tous sauf le dernier
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        history += f"{role}: {msg.content}\n"

    last_message = trimmed[-1].content

    # ── 3. Construit le message utilisateur pour Gemini ────
    # Gemini requiert toujours un HumanMessage non vide
    user_content = ""
    if history:
        user_content += f"Contexte récent de la conversation :\n{history}\n\n"
    user_content += f"Dernier message à analyser : {last_message}"

    # ── 4. Appelle Gemini ──────────────────────────────────
    response = await llm.ainvoke([
        SystemMessage(content=INTENT_PROMPT),
        HumanMessage(content=user_content),
    ])

    # ── 5. Parse le JSON ───────────────────────────────────
    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content.strip())
    except Exception:
        result = {"intent": "unknown", "target_agent": "none", "entities": {}}

    return {
        **state,
        "intent":       result.get("intent", "unknown"),
        "target_agent": result.get("target_agent", "none"),
        "entities":     result.get("entities", {}),
    }