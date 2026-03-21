# app/orchestrator/nodes/node1_intent.py
# ═══════════════════════════════════════════════════════════
# MIGRATION : ChatOllama (qwen3:4b local) → Groq GPT-OSS 20B
# Modèle léger pour la classification d'intention (économise les tokens)
# ═══════════════════════════════════════════════════════════
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from app.orchestrator.state import AssistantState
from dotenv import load_dotenv
import json
import os

load_dotenv()

# ── Groq GPT-OSS 20B via compatibilité OpenAI ─────────────
llm = ChatOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
    model="openai/gpt-oss-20b",
    temperature=0,
    max_tokens=512,
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


def _extract_clean_text(content: str) -> str:
    """
    Nettoie le content des AIMessage.
    Si c'est du JSON (réponse agent RH), extrait le champ "response".
    Sinon retourne le texte tel quel.
    """
    try:
        parsed = json.loads(content)
        return parsed.get("response", content)
    except (json.JSONDecodeError, TypeError):
        return content


async def node1_detect_intent(state: AssistantState) -> AssistantState:

    all_messages = state["messages"]
    trimmed = all_messages[-MAX_HISTORY_MESSAGES:] if len(all_messages) > MAX_HISTORY_MESSAGES else all_messages
    last_message = trimmed[-1].content

    # ── Debug : messages bruts dans le state ───────────────
    print(f"\n{'='*60}")
    print(f"🔍 NODE 1 — INTENT DETECTION")
    print(f"{'='*60}")
    print(f"📨 Dernier message : {last_message}")
    print(f"📚 Messages dans le state : {len(all_messages)} total → {len(trimmed)} après trim")

    # ── Construit l'historique NETTOYÉ ─────────────────────
    history = ""
    for i, msg in enumerate(trimmed[:-1]):
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        # ✅ FIX : nettoie les AIMessage (JSON → texte propre)
        if msg.type == "human":
            clean_content = msg.content
        else:
            clean_content = _extract_clean_text(msg.content)
        history += f"{role}: {clean_content}\n"

        # ── Debug : chaque message de l'historique ─────────
        is_cleaned = (clean_content != msg.content)
        tag = " 🧹 (nettoyé)" if is_cleaned else ""
        print(f"  [{i}] {role}{tag}: {clean_content[:120]}")

    print(f"{'─'*60}")

    # ── Construit le prompt final ──────────────────────────
    user_content = ""
    if history:
        user_content += f"Contexte récent :\n{history}\n\n"
    user_content += f"Dernier message : {last_message}"

    # ── Debug : ce que le LLM reçoit ──────────────────────
    print(f"📤 Prompt envoyé au LLM :")
    print(f"{user_content}")
    print(f"{'─'*60}")

    response = await llm.ainvoke([
        SystemMessage(content=INTENT_PROMPT),
        HumanMessage(content=user_content),
    ])

    # ── Debug : réponse brute du LLM ──────────────────────
    print(f"📥 Réponse brute LLM : {response.content[:200]}")

    try:
        content = response.content.strip()
        # GPT-OSS peut retourner du markdown — on nettoie
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        # GPT-OSS peut aussi inclure du texte avant/après le JSON
        # On cherche le premier { et le dernier }
        start_idx = content.find("{")
        end_idx = content.rfind("}") + 1
        if start_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx]
        result = json.loads(content.strip())
    except Exception as e:
        print(f"⚠️ Parsing JSON échoué ({e}) → fallback chat")
        result = {"intent": "chat", "target_agent": "none", "entities": {}}

    if result.get("intent") == "unknown":
        result = {"intent": "chat", "target_agent": "none", "entities": {}}

    # ── Debug : résultat final ─────────────────────────────
    print(f"✅ Résultat : intent={result.get('intent')} | agent={result.get('target_agent')} | entities={result.get('entities')}")
    print(f"{'='*60}\n")

    return {
        **state,
        "intent":       result.get("intent", "chat"),
        "target_agent": result.get("target_agent", "none"),
        "entities":     result.get("entities", {}),
    }