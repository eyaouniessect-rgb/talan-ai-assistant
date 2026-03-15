# Node 1 — Détection d'intention.
# Appelle le LLM avec le message utilisateur.
# Extrait :
#   - L'intention (create_leave, get_projects, get_tickets, search_docs, etc.)
#   - L'agent cible (agent_rh, agent_crm, agent_jira, agent_slack, agent_calendar, rag)
#   - Les entités nommées (dates, IDs de tickets, noms de projets)
# Charge aussi l'historique depuis PostgreSQL (long-term memory via Checkpointer).
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

INTENT_PROMPT = """
Tu es un analyseur d'intention pour un assistant d'entreprise.
Analyse le message utilisateur et retourne UNIQUEMENT un JSON valide.

Intentions possibles :
- create_leave        → agent: rh
- get_my_leaves       → agent: rh
- get_team_availability → agent: rh
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

Format de réponse OBLIGATOIRE :
{
  "intent": "nom_de_lintention",
  "target_agent": "nom_de_lagent",
  "entities": {}
}

Exemples d'entités :
- Pour create_leave : {"start_date": "2025-03-15", "end_date": "2025-03-21"}
- Pour create_ticket : {"title": "Bug login", "priority": "High", "project_key": "TAL"}
- Pour get_tickets : {"status_filter": "In Progress"}

Si aucune intention ne correspond, retourne :
{"intent": "unknown", "target_agent": "none", "entities": {}}
"""

async def node1_detect_intent(state: AssistantState) -> AssistantState:
    """
    Node 1 — Détecte l'intention du message utilisateur.
    Appelle Gemini pour analyser et extraire :
    - l'intention (create_leave, get_tickets...)
    - l'agent cible (rh, jira, crm...)
    - les entités (dates, IDs, titres...)
    """
    # Récupère le dernier message utilisateur
    last_message = state["messages"][-1].content

    response = await llm.ainvoke([
        SystemMessage(content=INTENT_PROMPT),
        HumanMessage(content=last_message),
    ])

    # Parse le JSON retourné par Gemini
    try:
        # Nettoie la réponse (Gemini peut ajouter des ```json ... ```)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content.strip())
    except Exception:
        result = {"intent": "unknown", "target_agent": "none", "entities": {}}

    return {
        **state,
        "intent": result.get("intent", "unknown"),
        "target_agent": result.get("target_agent", "none"),
        "entities": result.get("entities", {}),
    }