# app/orchestrator/nodes/node1_intent.py
# ═══════════════════════════════════════════════════════════
# Modèle : GPT-OSS 120B — classification d'intention + entités
# Date du jour injectée dynamiquement (avec jour de la semaine)
# ═══════════════════════════════════════════════════════════
from datetime import date
from langchain_core.messages import HumanMessage, SystemMessage
from app.orchestrator.state import AssistantState
from app.core.groq_client import invoke_with_fallback
from dotenv import load_dotenv
import json

load_dotenv()

MAX_HISTORY_MESSAGES = 10

INTENT_PROMPT = """
Tu es un analyseur d'intention pour un assistant d'entreprise.
Retourne UNIQUEMENT un JSON valide, sans markdown.

═══════════════════════════════════════════
RÈGLE PRINCIPALE — L'ACTION PRIME TOUJOURS
═══════════════════════════════════════════
Si le message contient un verbe d'action métier → utilise cet intent.
Peu importe le contexte. Peu importe les accents ou fautes de frappe.

INTENTIONS DISPONIBLES :
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
- update_event          → agent: calendar
- delete_event          → agent: calendar
- search_events         → agent: calendar
- check_availability    → agent: calendar
- search_docs           → agent: rag

Règle chat : UNIQUEMENT pour salutations seules, politesses finales, remerciements.
❌ "oui/non/ok/bien sûr" seuls → PAS chat (voir RÈGLE CONTEXTE)

═══════════════════════════════════════════
RÈGLE CONTEXTE — si le message N'a PAS d'action propre
═══════════════════════════════════════════
Si le message est ambigu (pas de verbe d'action clair) ET que l'assistant
vient de poser une question → c'est une réponse à cette question.
→ utilise l'intent de l'action en cours dans l'historique.

Détection "réponse à une question" :
  - Messages courts sans verbe d'action : "oui", "non", "14h", "bien sûr", "avec Meet",
    "déjeuner d'équipe", "lundi prochain", un email, un prénom, etc.
  → intent = même intent que l'action en cours

Détection "nouvelle action indépendante" :
  - Le message contient un verbe d'action (même sans accent, même avec fautes)
    ex: "creer", "planifie", "supprime", "modifie", "cree", "ajoute", "organise"
  → intent = nouvelle action, IGNORE le contexte

═══════════════════════════════════════════
CORRESPONDANCES CALENDAR
═══════════════════════════════════════════
create_event  = verbe créer/planifier/ajouter/organiser + événement quelconque
                (réunion, meeting, déjeuner, appel, standup, call, etc.)
update_event  = verbe modifier/changer/décaler/mettre à jour + événement existant
delete_event  = verbe supprimer/annuler/retirer + événement existant
get_calendar  = "montre", "affiche", "liste" + événements/réunions/agenda
check_availability = "disponible", "libre", "quelque chose de prévu", "conflits"
search_events = "cherche", "trouve" + événement

═══════════════════════════════════════════
EXEMPLES — L'ACTION PRIME
═══════════════════════════════════════════

Historique : Assistant: "Souhaitez-vous un Google Meet ?"
Message : "creer un reunion ce vendredi"
→ NOUVELLE ACTION (verbe "creer") → create_event  ← PAS chat

Historique : Assistant: "À quelle heure ?"
Message : "14h"
→ PAS de verbe d'action → CONTEXTE → create_event (hérite de l'historique)

Historique : Assistant: "Souhaitez-vous un Google Meet ?"
Message : "oui"
→ PAS de verbe d'action → CONTEXTE → create_event

Historique : Assistant: "Souhaitez-vous un Google Meet ?"
Message : "bien sûr"
→ PAS de verbe d'action → CONTEXTE → create_event

Historique : Assistant: "Quel est le titre exact ?"
Message : "déjeuner d'équipe"
→ PAS de verbe d'action → CONTEXTE → delete_event (hérite de l'historique)

Historique : Assistant: "Souhaitez-vous un Google Meet ?"
Message : "crée-moi un congé semaine prochaine"
→ NOUVELLE ACTION (verbe "crée") → create_leave  ← ignore le contexte calendar

Correction post-création :
Historique : Assistant: "Réunion créée ✅ ... sans lien Google Meet."
Message : "non la réunion est en ligne"
→ correction d'une action récente → update_event

═══════════════════════════════════════════
FORMAT OBLIGATOIRE
═══════════════════════════════════════════
JSON pur, sans markdown :
{"intent": "nom_intention", "target_agent": "nom_agent", "entities": {}}

Entités optionnelles :
- create_leave   : {"start_date": "2026-04-01", "end_date": "2026-04-05"}
- create_event   : {"title": "Réunion", "start_date": "2026-03-27", "start_time": "14:00", "end_time": "15:00"}
- get_calendar   : {"start_date": "2026-03-27", "end_date": "2026-03-28"}
- update_event   : {"event_id": "abc123", "title": "Nouveau titre"}
- delete_event   : {"event_id": "abc123"}
- search_events  : {"query": "réunion projet"}

N'extrais des dates QUE si explicitement mentionnées.
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

    _today = date.today()
    _JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    today_str = f"{_today.strftime('%Y-%m-%d')} ({_JOURS[_today.weekday()]})"
    intent_prompt_with_date = INTENT_PROMPT + f"\n\nDate du jour : {today_str}"

    response_content = await invoke_with_fallback(
        model="openai/gpt-oss-120b",
        messages=[
        SystemMessage(content=intent_prompt_with_date),
        HumanMessage(content=user_content),
        ],
        temperature=0,
        max_tokens=512,
    )

    # ── Debug : réponse brute du LLM ──────────────────────
    print(f"📥 Réponse brute LLM : {response_content[:200]}")

    try:
        content = response_content.strip()
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