# app/orchestrator/nodes/node1_intent.py
# ═══════════════════════════════════════════════════════════
# Node 1 — Routeur : classifie le message vers le bon AGENT
# ═══════════════════════════════════════════════════════════
from datetime import date
from langchain_core.messages import HumanMessage, SystemMessage
from app.orchestrator.state import AssistantState
from app.core.groq_client import invoke_with_fallback
from dotenv import load_dotenv
import json
import re as _re

load_dotenv()

MAX_HISTORY_MESSAGES = 10

# ══════════════════════════════════════════════════════════
# PROMPT — Classification par AGENT
# ══════════════════════════════════════════════════════════
ROUTER_PROMPT = """
Tu es un routeur pour un assistant d'entreprise.
Analyse le message et retourne UNIQUEMENT un JSON valide.

═══════════════════════════════════════════
AGENTS DISPONIBLES
═══════════════════════════════════════════
- rh        → congés, solde de congé, disponibilité équipe, compétences équipe, absence
- calendar  → réunions, meetings, agenda, créer/modifier/supprimer événement
- crm       → projets, clients, rapports
- jira      → tickets, bugs, tâches Jira
- slack     → envoyer messages Slack
- rag       → recherche documentaire
- chat      → salutations, politesses, remerciements UNIQUEMENT

═══════════════════════════════════════════
RÈGLE 1 — CHANGEMENT DE SUJET EXPLICITE
(PRIORITÉ LA PLUS HAUTE)
═══════════════════════════════════════════
Si le message contient une NOUVELLE ACTION EXPLICITE qui appartient
à un domaine DIFFÉRENT du contexte actuel → TOUJOURS suivre la nouvelle action.
Le contexte précédent ne compte plus.

Exemples CRITIQUES :
  Contexte calendar → "je veux créer un congé"      → rh (PAS calendar)
  Contexte calendar → "combien de jours de congé"   → rh (PAS calendar)
  Contexte calendar → "je serai absent lundi"        → rh (PAS calendar)
  Contexte rh       → "crée-moi une réunion demain"  → calendar (PAS rh)
  Contexte rh       → "montre mes tickets"           → jira (PAS rh)
  N'importe quel contexte → "envoie un message slack" → slack

⚠️ PIÈGE À ÉVITER : ne jamais rester sur l'agent précédent quand
l'utilisateur change clairement de sujet. Le verbe d'action + le domaine
suffisent pour rerouter.

═══════════════════════════════════════════
RÈGLE 2 — CONTINUATION DE CONTEXTE
═══════════════════════════════════════════
Si le message N'a PAS de verbe d'action pour un autre domaine
ET que l'assistant vient de poser une question
→ c'est une RÉPONSE → route vers le MÊME agent.

Messages qui sont des RÉPONSES (pas de changement de sujet) :
  "oui", "non", "14h", "ok", "d'accord", "bien sûr"
  un email (ex: "ahmed@talan.com")
  une date ou heure (ex: "demain à 10h", "lundi prochain")
  un nom de personne
  des infos combinées (ex: "ahmed@talan.com demain a 8h vers 8:30")
  → même agent que le contexte

═══════════════════════════════════════════
RÈGLE 3 — ACTION EXPLICITE SANS CONTEXTE
═══════════════════════════════════════════
Si le message contient une action claire → route vers l'agent concerné.

Exemples :
  "creer un reunion demain"       → calendar
  "je veux créer un congé"        → rh
  "montre mes tickets"            → jira
  "envoie un message à Ahmed"     → slack
  "cherche dans la doc"           → rag

═══════════════════════════════════════════
RÈGLE 4 — INTENTIONS IMPLICITES
═══════════════════════════════════════════
  "je suis malade demain"                  → rh
  "je serai absent lundi"                  → rh
  "je ne viens pas demain"                 → rh
  "compétences de l'équipe"                → rh
  "qui est disponible dans mon équipe"     → rh

═══════════════════════════════════════════
RÈGLE 5 — CHAT = CAS ULTRA RESTREINTS
═══════════════════════════════════════════
chat UNIQUEMENT pour :
  1. Salutation pure : "bonjour", "salut", "hello"
  2. Politesse pure : "au revoir", "bonne journée"
  3. Remerciement pur : "merci", "ok merci"

❌ "oui"/"non"/"ok" → PAS chat (voir RÈGLE 2)
❌ Si le moindre doute → NE PAS router vers chat

═══════════════════════════════════════════
FORMAT OBLIGATOIRE
═══════════════════════════════════════════
JSON pur, sans markdown :
{"target_agent": "nom_agent"}
"""


def _extract_clean_text(content: str) -> str:
    """Nettoie le content des AIMessage (JSON → texte propre)."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed.get("response", content)
        return content
    except (json.JSONDecodeError, TypeError):
        return content


# ══════════════════════════════════════════════════════════
# KEYWORDS par domaine
# ══════════════════════════════════════════════════════════
_AGENT_KEYWORDS = {
    "rh":       ["congé", "conge", "leave", "solde", "absence", "rh", "ressources humaines",
                 "malade", "maladie", "arrêt maladie", "arret maladie",
                 "je reste", "rester à la maison", "rester a la maison",
                 "je serai absent", "je suis absent", "je ne viens pas",
                 "je ne serai pas", "absent demain", "absent lundi", "pas au bureau",
                 "compétences", "competences", "stack", "disponibilité équipe",
                 "disponibilite equipe", "qui est disponible", "équipe disponible",
                 "membres de l'équipe", "membres de mon équipe",
                 "compétences de l'équipe", "competences de l'equipe",
                 "jours de congé", "jours de conge", "solde de congé",
                 "combien de jours", "reste de congé"],
    "calendar": ["réunion", "reunion", "meeting", "événement", "evenement", "agenda",
                 "calendrier", "meet", "google meet", "visio", "stand-up",
                 "standup", "call", "appel"],
    "jira":     ["ticket", "jira", "bug", "tâche", "tache", "sprint", "backlog"],
    "crm":      ["projet", "client", "rapport", "crm"],
    "slack":    ["slack", "canal", "channel"],
    "rag":      ["documentation", "cherche dans la doc"],
}

# Verbes qui indiquent une NOUVELLE action (pas une continuation)
_ACTION_VERBS = [
    "créer", "creer", "cree", "crée",
    "supprimer", "supprime",
    "modifier", "modifie",
    "déplacer", "deplacer", "décaler", "decaler",
    "consulter", "consulte", "voir", "montre", "affiche",
    "envoyer", "envoie", "envoi",
    "chercher", "cherche",
    "je veux", "je voudrais", "je souhaite",
    "combien", "quel est", "quelle est",
    "donne moi", "donne-moi", "donnez",
]

_CHAT_ONLY_TOKENS = {
    "bonjour", "salut", "hello", "bonsoir", "hi", "coucou",
    "merci", "ok merci", "super merci", "merci beaucoup",
    "au revoir", "bonne journée", "bonne journee", "à bientôt", "a bientot",
    "bonne soirée", "bonne soiree",
}

# Keywords dans les réponses AI pour identifier l'agent actif
_AI_CONTENT_KEYWORDS = {
    "rh":       ["congé", "jours ouvrés", "solde de congé", "demande de congé",
                 "jours disponibles", "manager notifié", "absence",
                 "compétences", "en congé", "équipe", "leave_balance"],
    "calendar": ["réunion", "événement", "google calendar", "google meet",
                 "créneau", "quelle heure", "planifier", "e-mail",
                 "adresse", "participants", "conflit"],
    "jira":     ["ticket", "jira", "sprint", "bug"],
    "crm":      ["projet", "client", "crm"],
    "slack":    ["slack", "message envoyé"],
}


def _is_chat_only(text: str) -> bool:
    clean = text.lower().strip().rstrip("!?.,")
    clean = " ".join(clean.split())
    return clean in _CHAT_ONLY_TOKENS


def _is_gibberish(text: str) -> bool:
    clean = text.lower().strip()
    if not clean:
        return True
    for keywords in _AGENT_KEYWORDS.values():
        if any(kw in clean for kw in keywords):
            return False
    if _is_chat_only(clean):
        return False
    alpha_only = _re.sub(r"[^a-zàâäéèêëïîôùûüÿçœæ]", "", clean)
    if len(alpha_only) < 3:
        return False
    voyelles = set("aeiouyàâäéèêëïîôùûüÿœæ")
    n_voyelles = sum(1 for c in alpha_only if c in voyelles)
    ratio = n_voyelles / len(alpha_only) if alpha_only else 0
    if len(alpha_only) >= 5 and ratio < 0.15:
        return True
    if _re.search(r"[^aeiouyàâäéèêëïîôùûüÿœæ]{6,}", alpha_only):
        return True
    return False


def _has_action_verb(text: str) -> bool:
    """Détecte si le message contient un verbe d'action explicite."""
    t = text.lower()
    return any(v in t for v in _ACTION_VERBS)


def _detect_agent_keywords(text: str) -> "str | None":
    """Retourne le nom de l'agent si le message contient des keywords de cet agent."""
    t = text.lower()
    for agent, keywords in _AGENT_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return agent
    return None


def _find_last_active_agent(messages: list) -> "str | None":
    """
    Cherche le dernier agent actif :
    1. Keywords dans les messages humains précédents
    2. Fallback : keywords dans le dernier message AI
    """
    for msg in reversed(messages[:-1]):
        if msg.type == "human":
            agent = _detect_agent_keywords(msg.content)
            if agent:
                return agent

    for msg in reversed(messages[:-1]):
        if msg.type != "human":
            content_lower = _extract_clean_text(msg.content).lower()
            for agent, keywords in _AI_CONTENT_KEYWORDS.items():
                if any(kw in content_lower for kw in keywords):
                    print(f"  🔍 Agent détecté via réponse AI → {agent}")
                    return agent
            break

    return None


def _detect_context_continuation(messages: list) -> "dict | None":
    """
    Logique de continuation de contexte améliorée :
    1. Si l'utilisateur change EXPLICITEMENT de sujet → return None (LLM décide)
    2. Si c'est une réponse à une question → continue le même agent
    """
    if len(messages) < 2:
        return None

    last_user_msg = messages[-1].content.strip()
    last_user_lower = last_user_msg.lower().rstrip("!?.,")
    last_ai_msg = None

    for msg in reversed(messages[:-1]):
        if msg.type != "human":
            last_ai_msg = _extract_clean_text(msg.content)
            break

    if not last_ai_msg:
        return None

    # L'assistant doit avoir posé une question
    if "?" not in last_ai_msg:
        return None

    # Salutation isolée → chat (ne pas forcer un agent)
    if _is_chat_only(last_user_lower):
        return None

    last_active = _find_last_active_agent(messages)
    if not last_active:
        return None

    # ── CHANGEMENT DE SUJET EXPLICITE ─────────────────────
    # Si le message contient des keywords d'un AUTRE agent
    # ET un verbe d'action → changement de sujet clair
    detected_agent = _detect_agent_keywords(last_user_lower)
    if detected_agent and detected_agent != last_active:
        if _has_action_verb(last_user_lower):
            print(f"  🔀 Changement de sujet explicite : {last_active} → {detected_agent}")
            return {"target_agent": detected_agent}
        # Keywords d'un autre agent mais pas de verbe d'action
        # ex: "congé" dans un contexte calendar → laisser le LLM trancher
        print(f"  🔀 Keywords autre agent détectés ({detected_agent}) sans verbe → LLM")
        return None

    # ── CONTINUATION ──────────────────────────────────────
    print(f"  🎯 Context continuation → {last_active}")
    return {"target_agent": last_active}


# ══════════════════════════════════════════════════════════
# NODE 1 — FONCTION PRINCIPALE
# ══════════════════════════════════════════════════════════
async def node1_detect_intent(state: AssistantState) -> AssistantState:

    all_messages = state["messages"]
    trimmed = all_messages[-MAX_HISTORY_MESSAGES:] if len(all_messages) > MAX_HISTORY_MESSAGES else all_messages
    last_message = trimmed[-1].content

    print(f"\n{'='*60}")
    print(f"🔍 NODE 1 — ROUTEUR (classification par agent)")
    print(f"{'='*60}")
    print(f"📨 Dernier message : {last_message}")
    print(f"📚 Messages : {len(all_messages)} total → {len(trimmed)} après trim")

    # ── Pré-check gibberish ──────────────────────────────
    if _is_gibberish(last_message):
        print(f"🚫 Message détecté comme gibberish → chat")
        print(f"{'='*60}\n")
        return {**state, "target_agent": "chat"}

    # ── Changement de sujet explicite (AVANT continuation) ─
    # Si le message a un verbe d'action + keywords d'un agent → route directement
    detected = _detect_agent_keywords(last_message.lower())
    if detected and _has_action_verb(last_message.lower()):
        last_active = _find_last_active_agent(trimmed)
        if last_active and last_active != detected:
            print(f"  🔀 Changement de sujet direct : {last_active} → {detected}")
            print(f"{'='*60}\n")
            return {**state, "target_agent": detected}

    # ── Continuation de contexte ──────────────────────────
    context_result = _detect_context_continuation(trimmed)
    if context_result:
        print(f"✅ Résultat (déterministe) : target_agent={context_result['target_agent']}")
        print(f"{'='*60}\n")
        return {**state, "target_agent": context_result["target_agent"]}

    # ── Construit l'historique nettoyé ────────────────────
    history = ""
    for i, msg in enumerate(trimmed[:-1]):
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        clean_content = msg.content if msg.type == "human" else _extract_clean_text(msg.content)
        history += f"{role}: {clean_content}\n"
        print(f"  [{i}] {role}: {clean_content[:300]}")

    print(f"{'─'*60}")

    # ── Prompt final ─────────────────────────────────────
    user_content = ""
    if history:
        user_content += f"Contexte récent :\n{history}\n\n"
    user_content += f"Dernier message : {last_message}"

    _today = date.today()
    _JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    today_str = f"{_today.strftime('%Y-%m-%d')} ({_JOURS[_today.weekday()]})"
    router_prompt_with_date = ROUTER_PROMPT + f"\n\nDate du jour : {today_str}"

    try:
        response_content = await invoke_with_fallback(
            model="openai/gpt-oss-120b",
            messages=[
                SystemMessage(content=router_prompt_with_date),
                HumanMessage(content=user_content),
            ],
            temperature=0,
            max_tokens=128,
        )
    except RuntimeError as e:
        print(f"⚠️ Node1 LLM indisponible ({str(e)[:80]}) → fallback keyword")
        for agent, keywords in _AGENT_KEYWORDS.items():
            if any(kw in last_message.lower() for kw in keywords):
                return {**state, "target_agent": agent}
        return {**state, "target_agent": "chat"}

    print(f"📥 Réponse brute LLM : {response_content[:200]}")

    try:
        content = response_content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        start_idx = content.find("{")
        end_idx = content.rfind("}") + 1
        if start_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx]
        result = json.loads(content.strip())
    except Exception as e:
        print(f"⚠️ Parsing JSON échoué ({e}) → fallback keyword")
        # Fallback keyword avant de tomber sur chat
        for agent, keywords in _AGENT_KEYWORDS.items():
            if any(kw in last_message.lower() for kw in keywords):
                return {**state, "target_agent": agent}
        result = {"target_agent": "chat"}

    target_agent = result.get("target_agent", "chat")

    valid_agents = {"rh", "calendar", "crm", "jira", "slack", "rag", "chat"}
    if target_agent not in valid_agents:
        print(f"⚠️ Agent inconnu '{target_agent}' → fallback keyword")
        for agent, keywords in _AGENT_KEYWORDS.items():
            if any(kw in last_message.lower() for kw in keywords):
                target_agent = agent
                break
        else:
            target_agent = "chat"

    print(f"✅ Résultat : target_agent={target_agent}")
    print(f"{'='*60}\n")

    return {**state, "target_agent": target_agent}
