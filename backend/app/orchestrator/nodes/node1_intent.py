# app/orchestrator/nodes/node1_intent.py
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from app.orchestrator.state import AssistantState
from dotenv import load_dotenv
import json

load_dotenv()

llm = ChatOllama(
    model="qwen3:4b-instruct-2507-q4_K_M",
    temperature=0,
    num_ctx=4096,
    num_predict=512,
    repeat_penalty=1.1,
)

MAX_HISTORY_MESSAGES = 6

INTENT_PROMPT = """
Tu es un analyseur d'intention pour un assistant d'entreprise.
Analyse le message utilisateur et retourne UNIQUEMENT un JSON valide, sans markdown.

═══════════════════════════════════════════
RÈGLE N°1 — PRIORITÉ À L'ACTION
═══════════════════════════════════════════
Si le message contient UNE action métier, utilise l'intention de l'action.

✅ "bonjour, je veux créer un congé"       → create_leave
✅ "salut, montre-moi mes projets"         → get_my_projects
✅ "bonjour c possible de créer un congé"  → create_leave
❌ "bonjour" seul                          → chat
❌ "c'est quoi la date ?"                  → chat (PAS get_calendar !)
❌ "quelle est la date aujourd'hui ?"      → chat (PAS get_calendar !)

get_calendar = UNIQUEMENT pour "montre-moi mon calendrier",
               "mes événements", "mes réunions"

═══════════════════════════════════════════
RÈGLE N°2 — MESSAGES CONVERSATIONNELS
═══════════════════════════════════════════
intent: chat si le message ne contient AUCUNE action :
- Salutations          : "bonjour", "salut", "hello"
- Remerciements        : "merci", "ok merci", "super", "parfait"
- Confirmations        : "ok", "d'accord"
- Politesse            : "au revoir", "bonne journée"
- Questions sur la date: "c'est quoi la date", "quel jour sommes-nous"
- Questions contextuelles : "qu'est-ce qu'on a fait", "rappelle-moi"

═══════════════════════════════════════════
INTENTIONS DISPONIBLES
═══════════════════════════════════════════
- chat                  → agent: none
- create_leave          → agent: rh
- check_leave_balance   → agent: rh
- get_my_leaves         → agent: rh
- get_team_availability → agent: rh
- get_team_stack        → agent: rh
- get_my_projects       → agent: crm
- get_all_projects      → agent: crm
- generate_report       → agent: crm
- get_tickets           → agent: jira
- create_ticket         → agent: jira
- update_ticket         → agent: jira
- send_message          → agent: slack
- get_calendar          → agent: calendar
- create_event          → agent: calendar
- search_docs           → agent: rag

═══════════════════════════════════════════
FORMAT OBLIGATOIRE
═══════════════════════════════════════════
JSON pur, sans markdown :
{"intent": "nom_intention", "target_agent": "nom_agent", "entities": {}}

Exemples :
- create_leave        : {"start_date": "2026-04-01", "end_date": "2026-04-05"}
- check_leave_balance : {"requested_days": 5}
- create_ticket       : {"title": "Bug login", "priority": "High"}

═══════════════════════════════════════════
RÈGLES COMPLÉMENTAIRES
═══════════════════════════════════════════
- Contexte ("du 15 au 21", "oui confirme") → utilise l'historique
- unknown = SEULEMENT si totalement incompréhensible
- En cas de doute → préfère TOUJOURS chat

═══════════════════════════════════════════
RÈGLE ENTITÉS — DATES
═══════════════════════════════════════════
N'extrais des dates QUE si explicitement mentionnées.
✅ "congé du 20 au 25 avril" → {"start_date": "2026-04-20", "end_date": "2026-04-25"}
❌ "je veux créer un congé"  → {"entities": {}}
"""


async def node1_detect_intent(state: AssistantState) -> AssistantState:

    all_messages = state["messages"]
    trimmed = all_messages[-MAX_HISTORY_MESSAGES:] if len(all_messages) > MAX_HISTORY_MESSAGES else all_messages
    last_message = trimmed[-1].content

    history = ""
    for msg in trimmed[:-1]:
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        history += f"{role}: {msg.content}\n"

    user_content = ""
    if history:
        user_content += f"Contexte récent :\n{history}\n\n"
    user_content += f"Dernier message : {last_message}"

    response = await llm.ainvoke([
        SystemMessage(content=INTENT_PROMPT),
        HumanMessage(content=user_content),
    ])

    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content.strip())
    except Exception:
        result = {"intent": "chat", "target_agent": "none", "entities": {}}

    if result.get("intent") == "unknown":
        result = {"intent": "chat", "target_agent": "none", "entities": {}}

    return {
        **state,
        "intent":       result.get("intent", "chat"),
        "target_agent": result.get("target_agent", "none"),
        "entities":     result.get("entities", {}),
    }