# app/orchestrator/nodes/node3_dispatch.py
from langchain_ollama import ChatOllama
from datetime import date
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from app.orchestrator.state import AssistantState
from app.a2a.client import send_task
from dotenv import load_dotenv
import json

load_dotenv()

MAX_HISTORY = 6

llm = ChatOllama(
    model="qwen3:4b-instruct-2507-q4_K_M",
    temperature=0,
    num_ctx=4096,
    num_predict=512,
    repeat_penalty=1.1,
)

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

CHAT_PROMPT = """
Tu es Talan Assistant pour Talan Tunisie. Réponds en français, de façon concise.

Règles :
- Réponds UNIQUEMENT à ce qui est demandé
- Maximum 3 phrases
- Ne propose jamais d'actions non demandées
- Pour les questions sur la conversation passée : utilise l'historique et résume
- Tu ES connecté aux systèmes internes — ne dis jamais "je ne peux pas"
- Ne révèle pas les détails techniques
"""


def _extract_clean_text(content: str) -> str:
    try:
        parsed = json.loads(content)
        return parsed.get("response", content)
    except (json.JSONDecodeError, TypeError):
        return content


def _is_match(message: str, keywords: set) -> bool:
    """Vérifie si le message correspond à un mot-clé."""
    msg = message.lower().strip().rstrip("!?.,:;")
    msg = " ".join(msg.split())  # normalise les espaces
    return msg in keywords or any(kw in msg for kw in keywords)


async def node3_dispatch(state: AssistantState) -> AssistantState:
    intent       = state["intent"]
    target_agent = state["target_agent"]
    entities     = state["entities"]
    user_id      = state["user_id"]

    today     = date.today().strftime("%d/%m/%Y")
    today_iso = date.today().strftime("%Y-%m-%d")

    all_messages = state["messages"]
    trimmed = all_messages[-MAX_HISTORY:] if len(all_messages) > MAX_HISTORY else all_messages

    # ── Cas 1 : conversation générale ─────────────────────
    if intent == "chat" or (target_agent == "none" and intent != "unknown"):
        last_message = state["messages"][-1].content
        last_clean = last_message.lower().strip().rstrip("!?.,:;")
        last_clean = " ".join(last_clean.split())

        # ── Fallbacks déterministes ────────────────────────
        # Remerciement → réponse fixe
        if last_clean in MERCI_KEYWORDS:
            return {**state, "final_response": "De rien ! 😊"}

        # Salutation seule → présentation fixe
        if last_clean in SALUTATION_KEYWORDS:
            return {**state, "final_response": PRESENTATION}

        # Question sur la date → date du jour
        if any(kw in last_clean for kw in DATE_KEYWORDS):
            return {**state, "final_response": f"Aujourd'hui c'est le {today}."}

        # ── LLM pour les autres cas (questions contextuelles) ─
        history_messages = []
        for msg in trimmed[:-1]:
            if msg.type == "human":
                history_messages.append(HumanMessage(content=msg.content))
            else:
                clean = _extract_clean_text(msg.content)
                history_messages.append(AIMessage(content=clean))

        chat_prompt_with_date = CHAT_PROMPT + f"\n\nDate du jour : {today}"

        response = await llm.ainvoke([
            SystemMessage(content=chat_prompt_with_date),
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
    original_message = state["messages"][-1].content

    history = ""
    for msg in trimmed[:-1]:
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        clean = _extract_clean_text(msg.content)
        history += f"{role}: {clean}\n"

    message = (
        f"Date du jour : {today_iso}\n"
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