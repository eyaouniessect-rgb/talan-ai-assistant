# app/orchestrator/nodes/node3_dispatch.py
# ═══════════════════════════════════════════════════════════
# Node 3 — Dispatch simplifié
# Reçoit target_agent de Node 1, découvre l'agent, et dispatch.
# Plus de mapping intent→skill. L'agent décide lui-même quel tool appeler.
# ═══════════════════════════════════════════════════════════
from datetime import date
from langchain_core.messages import HumanMessage, AIMessage
from app.orchestrator.state import AssistantState
from app.a2a.client import send_task_to_url
from app.a2a.discovery import discovery
from dotenv import load_dotenv
import json

load_dotenv()

MAX_HISTORY = 10

# ── Réponses déterministes pour les cas simples ────────────
MERCI_KEYWORDS = {
    "merci", "ok merci", "super merci", "merci beaucoup",
    "parfait", "super", "nickel", "très bien", "d'accord",
    "ok d'accord", "c'est bon", "c bon"
}

DATE_KEYWORDS = {
    "date", "aujourd'hui", "quel jour", "quelle date",
    "c'est quoi la date", "la date aujourd'hui", "date du jour"
}

SALUTATION_KEYWORDS = {
    "bonjour", "salut", "hello", "bonsoir", "hi", "coucou", "bonne journée"
}

PRESENTATION = """Bonjour ! Je suis Talan Assistant chez Talan Tunisie.
Je peux vous aider avec vos congés, projets, tickets Jira, messages Slack, calendrier et recherche documentaire.
Comment puis-je vous aider ?"""

_AU_REVOIR_KEYWORDS = {
    "au revoir", "aurevoir", "bonne journée", "bonne journee",
    "à bientôt", "a bientot", "bonne soirée", "bonne soiree",
    "bye", "ciao", "tchao",
}


def _extract_clean_text(content: str) -> str:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed.get("response", content)
        return content
    except (json.JSONDecodeError, TypeError):
        return content


def _is_match(message: str, keywords: set) -> bool:
    msg = message.lower().strip().rstrip("!?.,:;")
    msg = " ".join(msg.split())
    return msg in keywords or any(kw in msg for kw in keywords)


async def node3_dispatch(state: AssistantState) -> AssistantState:
    target_agent = state["target_agent"]
    user_id      = state["user_id"]
    role         = state["role"]

    _today = date.today()
    _JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    today_day = _JOURS[_today.weekday()]
    today     = _today.strftime("%d/%m/%Y")
    today_iso = f"{_today.strftime('%Y-%m-%d')} ({today_day})"

    all_messages = state["messages"]
    trimmed = all_messages[-MAX_HISTORY:] if len(all_messages) > MAX_HISTORY else all_messages

    print(f"\n{'='*60}")
    print(f"📡 NODE 3 — DISPATCH")
    print(f"{'='*60}")
    print(f"🎯 Target agent: {target_agent} | Role: {role}")
    print(f"📚 Messages: {len(all_messages)} total → {len(trimmed)} après trim")

    # ══════════════════════════════════════════════════════
    # Cas 1 : conversation générale (chat)
    # ══════════════════════════════════════════════════════
    # PAS de LLM ici → réponses déterministes uniquement.
    # Tout le reste est un message mal routé → message d'aide.
    if target_agent == "chat":
        last_message = state["messages"][-1].content
        last_clean = last_message.lower().strip().rstrip("!?.,:;")
        last_clean = " ".join(last_clean.split())

        if last_clean in MERCI_KEYWORDS:
            print(f"💬 Déterministe : MERCI")
            print(f"{'='*60}\n")
            return {**state, "final_response": "De rien ! N'hésitez pas si vous avez besoin d'autre chose."}

        if last_clean in SALUTATION_KEYWORDS:
            print(f"💬 Déterministe : SALUTATION")
            print(f"{'='*60}\n")
            return {**state, "final_response": PRESENTATION}

        if last_clean in _AU_REVOIR_KEYWORDS:
            print(f"💬 Déterministe : AU REVOIR")
            print(f"{'='*60}\n")
            return {**state, "final_response": "Au revoir ! Bonne continuation."}

        if any(kw in last_clean for kw in DATE_KEYWORDS):
            print(f"💬 Déterministe : DATE → {today}")
            print(f"{'='*60}\n")
            return {**state, "final_response": f"Aujourd'hui c'est le {today}."}

        # Fallback — message non reconnu, pas de LLM
        print(f"💬 Déterministe : FALLBACK (message non reconnu)")
        print(f"   Message : {last_message[:120]}")
        print(f"{'='*60}\n")
        fallback = (
            "Je n'ai pas compris votre demande. Voici ce que je peux faire :\n\n"
            "- **Congés** : créer, consulter, vérifier le solde\n"
            "- **Calendrier** : créer, modifier, supprimer des réunions\n"
            "- **Jira** : consulter vos tickets\n"
            "- **Slack** : envoyer un message\n\n"
            "Pouvez-vous reformuler votre demande ?"
        )
        return {**state, "final_response": fallback}

    # ══════════════════════════════════════════════════════
    # Cas 2 : dispatch vers un agent A2A
    # ══════════════════════════════════════════════════════
    print(f"🔍 Discovery — recherche agent '{target_agent}'...")

    discovered_agent = await discovery.find_agent_by_name(target_agent)

    if discovered_agent:
        agent_url = discovered_agent.url
        agent_name = discovered_agent.name
        print(f"✅ Agent trouvé : '{agent_name}' à {agent_url}")
        print(f"   Skills : {discovered_agent.skills}")
    else:
        # Fallback : registry statique
        print(f"⚠️ Agent '{target_agent}' non découvert, tentative registry...")
        from app.a2a.registry import get_agent_url
        try:
            agent_url = get_agent_url(target_agent)
            agent_name = target_agent
        except ValueError:
            print(f"❌ Agent '{target_agent}' introuvable")
            print(f"{'='*60}\n")
            return {
                **state,
                "final_response": (
                    f"L'agent {target_agent} est temporairement indisponible. "
                    f"Veuillez réessayer plus tard."
                )
            }

    # ── Construit le message enrichi pour l'agent ────────
    original_message = state["messages"][-1].content

    history = ""
    for i, msg in enumerate(trimmed[:-1]):
        r = "Utilisateur" if msg.type == "human" else "Assistant"
        clean = _extract_clean_text(msg.content)
        history += f"{r}: {clean}\n"
        print(f"  [{i}] {r}: {clean[:120]}")

    message = (
        f"Date du jour : {today_iso}\n"
        f"Historique récent de la conversation :\n{history}\n"
        f"---\n"
        f"Message utilisateur : {original_message}\n"
        f"Role utilisateur : {role}\n"
        f"User ID : {user_id}"
    )

    print(f"{'─'*60}")
    print(f"📤 Envoi à '{agent_name}' ({agent_url})")
    print(f"{'─'*60}")

    try:
        response = await send_task_to_url(agent_url, message)
        print(f"📥 Réponse agent : {str(response)[:200]}")
    except Exception as e:
        print(f"❌ Erreur agent '{agent_name}' : {str(e)}")
        _QUOTA_SIGNALS = ("request too large", "tokens per minute", "413", "context_length")
        if any(sig in str(e).lower() for sig in _QUOTA_SIGNALS):
            response = (
                "⚠️ Le service IA est temporairement indisponible : limite de tokens atteinte.\n"
                "Cela se produit lorsque la conversation est très longue ou que le quota minute est épuisé.\n"
                "**Que faire ?**\n"
                "- Patientez quelques secondes et réessayez\n"
                "- Ou démarrez une nouvelle conversation (bouton ✚ en haut à gauche)"
            )
        else:
            response = (
                f"L'agent {agent_name} est temporairement indisponible. "
                f"Erreur : {str(e)}"
            )

    print(f"{'='*60}\n")
    return {**state, "final_response": response}
