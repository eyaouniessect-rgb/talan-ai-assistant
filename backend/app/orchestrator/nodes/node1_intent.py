# app/orchestrator/nodes/node1_intent.py
# ═══════════════════════════════════════════════════════════
# Node 1 — Routeur LLM-first (refactorisé)
#
# Architecture :
#   FAST PATH 1 → chat-only (salutations, remerciements) — sans LLM
#   FAST PATH 2 → gibberish — sans LLM
#   FAST PATH 3 → context continuation stricte — sans LLM
#                 (réponse courte à une question, state["target_agent"] comme référence)
#   PRIMARY     → LLM router avec Agent Cards compactes + few-shots
#   FALLBACK    → keyword match d'urgence si LLM indisponible
#
# Principe fondamental : le DOMAINE décide, pas le verbe d'action.
# target_agents est TOUJOURS réinitialisé à None sauf dispatch multi-agent explicite.
# ═══════════════════════════════════════════════════════════

from datetime import date
from langchain_core.messages import HumanMessage, SystemMessage
from app.orchestrator.state import AssistantState
from app.core.groq_client import invoke_with_fallback
from app.a2a.discovery import routing_manifest
from dotenv import load_dotenv
from langsmith import traceable
import json
import re as _re
import unicodedata as _unicodedata

load_dotenv()

# Historique : 6 messages suffisent pour le contexte, évite le context overflow
MAX_HISTORY_MESSAGES = 6
# Longueur max d'un message AI dans l'historique envoyé au routeur
MAX_AI_CHARS_IN_HISTORY = 300

# ══════════════════════════════════════════════════════════
# FAST PATH — Tokens chat-only (sans LLM)
# ══════════════════════════════════════════════════════════
_CHAT_ONLY_TOKENS = {
    "bonjour", "salut", "hello", "bonsoir", "hi", "coucou",
    "merci", "ok merci", "super merci", "merci beaucoup",
    "au revoir", "bonne journée", "bonne journee", "à bientôt", "a bientot",
    "bonne soirée", "bonne soiree",
}

# ══════════════════════════════════════════════════════════
# FAST PATH — Verbes d'action (utilisés UNIQUEMENT pour
# la context continuation : si présent → pas une réponse)
# ══════════════════════════════════════════════════════════
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
    "poser", "pose", "planifier", "planifie",
    "organiser", "organise", "annuler", "annule",
    "vérifier", "verifie", "vérifie",
    "retirer", "retire",
    "mettre à jour", "mets à jour", "mets a jour",
]

# ══════════════════════════════════════════════════════════
# PROMPT LLM ROUTEUR — Agent Cards injectées dynamiquement
# ══════════════════════════════════════════════════════════
ROUTER_SYSTEM_PROMPT = """\
Tu es le routeur d'un assistant d'entreprise multi-agents.
Ta seule mission : analyser le message et retourner un JSON indiquant quel(s) agent(s) traite(nt) la demande.

{agents_section}

══════════════════════════════════════════
RÈGLE 1 — LE DOMAINE DÉCIDE (pas le verbe)
══════════════════════════════════════════
Le SUJET détermine l'agent, pas le verbe. Mêmes verbes, domaines différents :
  "supprimer un CONGÉ"       → rh       | "supprimer une RÉUNION"    → calendar
  "créer un CONGÉ"           → rh       | "créer une RÉUNION"        → calendar
  "annuler mon ABSENCE"      → rh       | "annuler un MEETING"       → calendar
  "modifier mes jours de RH" → rh       | "modifier le PLANNING"     → calendar

══════════════════════════════════════════
RÈGLE 2 — CONTEXTE CONVERSATIONNEL
══════════════════════════════════════════
L'historique récent est fourni pour contexte. Si le message actuel contient
une action explicite dans un NOUVEAU domaine → route vers le NOUVEL agent.
Ne pas rester sur l'agent précédent si le sujet change clairement.

══════════════════════════════════════════
RÈGLE 3 — MULTI-AGENT
══════════════════════════════════════════
Multi-agent si :
  1. 2+ actions dans des DOMAINES DIFFÉRENTS (agents différents)
  2. Chaque action est INDÉPENDANTE (pas une condition de l'autre)
  3. Présence d'un connecteur ou d'une liste : "et", "aussi", "en plus", "puis", "+", virgule entre actions distinctes

Supporte 2 agents ET 3 agents ou plus.
Format 3 agents : {{"targets": [{{"agent":"rh","sub_task":"..."}},{{"agent":"calendar","sub_task":"..."}},{{"agent":"jira","sub_task":"..."}}]}}

❌ PAS multi-agent si :
  • deux actions du même domaine → un seul agent suffit
  • une action + une condition / précision
  • une seule action principale

══════════════════════════════════════════
RÈGLE 4 — CHAT (ultra restreint)
══════════════════════════════════════════
chat uniquement pour : salutations pures, politesse, remerciements.
Si le moindre doute → NE PAS router vers chat.

══════════════════════════════════════════
EXEMPLES FEW-SHOT
══════════════════════════════════════════
"supprimer mon congé de demain"                     → {{"target_agent": "rh"}}
"annule la réunion avec le client"                  → {{"target_agent": "calendar"}}
"décaler la réunion de test la semaine prochaine"   → {{"target_agent": "calendar"}}
"supprime mon absence de lundi"                     → {{"target_agent": "rh"}}
"montre mes congés en attente"                      → {{"target_agent": "rh"}}
"qu'est-ce que j'ai comme réunions cette semaine ?" → {{"target_agent": "calendar"}}
"combien de jours de congé il me reste ?"           → {{"target_agent": "rh"}}
"qui est disponible dans mon équipe lundi ?"        → {{"target_agent": "rh"}}
"pose un congé lundi ET crée une réunion mardi"     → {{"targets": [{{"agent": "rh", "sub_task": "pose un congé lundi"}}, {{"agent": "calendar", "sub_task": "crée une réunion mardi"}}]}}
"annule mon congé et montre mes réunions de la semaine" → {{"targets": [{{"agent": "rh", "sub_task": "annule mon congé"}}, {{"agent": "calendar", "sub_task": "montre mes réunions de la semaine"}}]}}
"vérifie mon solde de congés puis montre moi mon agenda de la semaine prochaine" → {{"targets": [{{"agent": "rh", "sub_task": "vérifie mon solde de congés"}}, {{"agent": "calendar", "sub_task": "montre mon agenda de la semaine prochaine"}}]}}
"pose un congé lundi, crée une réunion mardi et mets à jour mon ticket jira en cours" → {{"targets": [{{"agent": "rh", "sub_task": "pose un congé lundi"}}, {{"agent": "calendar", "sub_task": "crée une réunion mardi"}}, {{"agent": "jira", "sub_task": "mets à jour mon ticket jira en cours"}}]}}
"supprimer mon congé et vérifier mon solde"         → {{"target_agent": "rh"}} (même domaine RH)
"décaler la réunion de test vendredi"               → {{"target_agent": "calendar"}} (1 seule action)
"bonjour"                                           → {{"target_agent": "chat"}}

══════════════════════════════════════════
FORMAT DE SORTIE (JSON strict, sans markdown)
══════════════════════════════════════════
Agent unique  : {{"target_agent": "nom_agent"}}
Multi-agent   : {{"targets": [{{"agent": "nom1", "sub_task": "tâche1"}}, {{"agent": "nom2", "sub_task": "tâche2"}}]}}

Date du jour  : {today}
"""


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════

def _extract_clean_text(content: str) -> str:
    """Nettoie le content des AIMessage (JSON → texte propre)."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed.get("response", content)
        return content
    except (json.JSONDecodeError, TypeError):
        return content


def _is_chat_only(text: str) -> bool:
    clean = text.lower().strip().rstrip("!?.,")
    clean = " ".join(clean.split())
    return clean in _CHAT_ONLY_TOKENS


def _has_action_verb(text: str) -> bool:
    t = text.lower()
    return any(v in t for v in _ACTION_VERBS)


def _is_gibberish(text: str) -> bool:
    """
    Détecte le gibberish par analyse linguistique simple.
    Indépendant du keyword map — fonctionne pour n'importe quel nombre d'agents.
    """
    clean = text.lower().strip()
    if not clean:
        return True
    if _is_chat_only(clean):
        return False
    # Retire les non-lettres pour l'analyse phonétique
    alpha_only = _re.sub(r"[^a-zàâäéèêëïîôùûüÿçœæ]", "", clean)
    if len(alpha_only) < 3:
        return False
    voyelles = set("aeiouyàâäéèêëïîôùûüÿœæ")
    n_voyelles = sum(1 for c in alpha_only if c in voyelles)
    ratio = n_voyelles / len(alpha_only) if alpha_only else 0
    # Trop peu de voyelles → probablement du gibberish
    if len(alpha_only) >= 5 and ratio < 0.15:
        return True
    # Suite de consonnes impossibles en français
    if _re.search(r"[^aeiouyàâäéèêëïîôùûüÿœæ]{6,}", alpha_only):
        return True
    return False


def _is_short_reply(text: str) -> bool:
    """True si le message est manifestement une courte réponse (date, heure, nom, oui/non...)."""
    t = text.strip()
    if len(t) > 80:
        return False
    if _has_action_verb(t.lower()):
        return False
    return True


def _build_history_for_llm(trimmed_messages: list) -> str:
    """Construit un historique compact pour le prompt du routeur (sans le dernier message)."""
    lines = []
    for msg in trimmed_messages[:-1]:
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        content = msg.content if msg.type == "human" else _extract_clean_text(msg.content)
        # Tronque les longues réponses AI
        if msg.type != "human" and len(content) > MAX_AI_CHARS_IN_HISTORY:
            content = content[:MAX_AI_CHARS_IN_HISTORY] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_llm_json(raw: str) -> dict | None:
    """Extrait et parse le JSON de la réponse LLM (tolère le markdown)."""
    content = raw.strip()
    if "```" in content:
        parts = content.split("```")
        content = parts[1] if len(parts) > 1 else content
        if content.startswith("json"):
            content = content[4:]
    start = content.find("{")
    end = content.rfind("}") + 1
    if start != -1 and end > start:
        content = content[start:end]
    try:
        return json.loads(content.strip())
    except Exception:
        return None


# ══════════════════════════════════════════════════════════
# FALLBACK — keyword match d'urgence (LLM indisponible)
# ══════════════════════════════════════════════════════════

def _normalize_french(text: str) -> str:
    """Retire les accents et corrige les typos françaises courantes."""
    _FIXES = {
        "conje": "conge", "conjes": "conges", "conjer": "conger",
        "réuion": "reunion", "reunoin": "reunion",
        "absense": "absence", "absance": "absence",
    }
    nfkd = _unicodedata.normalize("NFD", text)
    normalized = "".join(c for c in nfkd if _unicodedata.category(c) != "Mn")
    for typo, fix in _FIXES.items():
        normalized = normalized.replace(typo, fix)
    return normalized


def _keyword_fallback(text: str, keyword_map: dict[str, set[str]]) -> str | None:
    """
    Fallback keyword match pondéré.
    UNIQUEMENT utilisé quand le LLM est indisponible.
    """
    t = text.lower()
    t_norm = _normalize_french(t)
    t_words = set(_re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ]+", t))
    t_norm_words = set(_re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ]+", t_norm))

    scores: dict[str, float] = {}
    for agent, tags in keyword_map.items():
        score = 0.0
        for kw in tags:
            kw_lower = kw.lower()
            matched = kw_lower in t or kw_lower in t_norm
            if not matched and " " in kw_lower:
                kw_words = set(kw_lower.split())
                matched = kw_words.issubset(t_words) or kw_words.issubset(t_norm_words)
            if matched:
                word_count = len(kw_lower.split())
                weight = word_count * 2.0 if word_count > 1 else 1.0
                if len(kw_lower) > 8:
                    weight += 1.0
                score += weight
        if score > 0:
            scores[agent] = score

    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # Si ambiguïté forte → None (caller choisira le fallback ultime)
    if len(ranked) >= 2:
        best, second = ranked[0][1], ranked[1][1]
        if best > 0 and (best - second) / best < 0.25:
            return None
    return ranked[0][0]


# ══════════════════════════════════════════════════════════
# NODE 1 — FONCTION PRINCIPALE
# ══════════════════════════════════════════════════════════
@traceable(
    name="node1_detect_intent",
    run_type="chain",
    tags=["orchestrator", "routing"],
    metadata={"node": "node1"},
)
async def node1_detect_intent(state: AssistantState) -> AssistantState:
    """
    Routeur LLM-first.
    Retourne toujours target_agent + target_agents (None sauf multi-agent explicite).
    """

    # ── Charger le manifest ───────────────────────────────
    manifest = await routing_manifest.build()
    valid_agents = manifest.agent_names | {"chat", "rag"}

    all_messages = state["messages"]
    trimmed = (
        all_messages[-MAX_HISTORY_MESSAGES:]
        if len(all_messages) > MAX_HISTORY_MESSAGES
        else all_messages
    )
    last_message = trimmed[-1].content

    _today = date.today()
    _JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    today_str = f"{_today.strftime('%Y-%m-%d')} ({_JOURS[_today.weekday()]})"

    print(f"\n{'='*60}")
    print(f"🔍 NODE 1 — ROUTEUR LLM-FIRST")
    print(f"{'='*60}")
    print(f"📨 Message : {last_message[:120]}")
    print(f"📚 {len(all_messages)} msgs total → {len(trimmed)} trimmed | {len(valid_agents)-2} agents actifs")

    # ╔══════════════════════════════════════════════════════╗
    # ║  FAST PATH 1 — Chat-only (sans LLM)                 ║
    # ╚══════════════════════════════════════════════════════╝
    if _is_chat_only(last_message):
        print(f"✅ FAST PATH: chat-only token")
        print(f"{'='*60}\n")
        return {**state, "target_agent": "chat", "target_agents": None}

    # ╔══════════════════════════════════════════════════════╗
    # ║  FAST PATH 2 — Gibberish (sans LLM)                 ║
    # ╚══════════════════════════════════════════════════════╝
    if _is_gibberish(last_message):
        print(f"🚫 FAST PATH: gibberish → chat")
        print(f"{'='*60}\n")
        return {**state, "target_agent": "chat", "target_agents": None}

    # ╔══════════════════════════════════════════════════════╗
    # ║  FAST PATH 3 — Context continuation stricte (sans LLM) ║
    # ║  Utilise state["target_agent"] comme référence      ║
    # ╚══════════════════════════════════════════════════════╝
    last_active_agent = state.get("target_agent")

    if last_active_agent and last_active_agent not in ("chat", "rag"):
        # Trouve le dernier message AI
        last_ai_msg = None
        for msg in reversed(trimmed[:-1]):
            if msg.type != "human":
                last_ai_msg = _extract_clean_text(msg.content)
                break

        # Continuation seulement si : AI a posé une question ET réponse courte sans verbe
        if last_ai_msg and "?" in last_ai_msg and _is_short_reply(last_message):
            print(f"✅ FAST PATH: context continuation → {last_active_agent}")
            print(f"   (réponse courte à une question, pas de verbe d'action)")
            print(f"{'='*60}\n")
            return {**state, "target_agent": last_active_agent, "target_agents": None}

    # ╔══════════════════════════════════════════════════════╗
    # ║  PRIMARY — LLM Router avec Agent Cards + few-shots  ║
    # ╚══════════════════════════════════════════════════════╝
    history = _build_history_for_llm(trimmed)

    # Log de l'historique
    for line in history.splitlines()[:6]:
        print(f"  {line[:120]}")
    print(f"{'─'*60}")

    agents_section = manifest.routing_prompt or (
        "AGENTS : rh (congés/RH), calendar (réunions/agenda), chat (salutations)"
    )

    system_prompt = ROUTER_SYSTEM_PROMPT.format(
        agents_section=agents_section,
        today=today_str,
    )

    user_content = ""
    if history.strip():
        user_content += f"Historique récent :\n{history}\n\n"
    user_content += f"Message à router : {last_message}"

    try:
        raw_response = await invoke_with_fallback(
            model="openai/gpt-oss-20b",
            messages=[
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ],
            temperature=0,
            max_tokens=300,
        )
    except RuntimeError as e:
        print(f"⚠️ LLM indisponible ({str(e)[:60]}) → fallback keyword")
        fb = _keyword_fallback(last_message.lower(), manifest.keyword_map)
        print(f"{'='*60}\n")
        return {**state, "target_agent": fb or "chat", "target_agents": None}

    print(f"📥 LLM brut : {raw_response[:200]}")

    result = _parse_llm_json(raw_response)

    if result is None:
        print(f"⚠️ JSON invalide → fallback keyword")
        fb = _keyword_fallback(last_message.lower(), manifest.keyword_map)
        print(f"{'='*60}\n")
        return {**state, "target_agent": fb or "chat", "target_agents": None}

    # ── Cas multi-agent ──────────────────────────────────
    if "targets" in result and isinstance(result["targets"], list):
        targets = result["targets"]
        valid_targets = [
            t for t in targets
            if isinstance(t, dict)
            and t.get("agent") in valid_agents
            and t.get("sub_task")
        ]
        if len(valid_targets) >= 2:
            print(f"✅ MULTI-AGENT : {[t['agent'] for t in valid_targets]}")
            print(f"{'='*60}\n")
            return {
                **state,
                "target_agent": valid_targets[0]["agent"],
                "target_agents": valid_targets,
            }
        # Dégradation : 1 seul target valide → mono-agent
        if len(valid_targets) == 1:
            print(f"✅ Résultat (multi→mono) : {valid_targets[0]['agent']}")
            print(f"{'='*60}\n")
            return {**state, "target_agent": valid_targets[0]["agent"], "target_agents": None}

    # ── Cas mono-agent ───────────────────────────────────
    target_agent = result.get("target_agent", "chat")

    if target_agent not in valid_agents:
        print(f"⚠️ Agent '{target_agent}' inconnu → fallback keyword")
        fb = _keyword_fallback(last_message.lower(), manifest.keyword_map)
        target_agent = fb or "chat"

    print(f"✅ Résultat : target_agent={target_agent}")
    print(f"{'='*60}\n")
    return {**state, "target_agent": target_agent, "target_agents": None}
