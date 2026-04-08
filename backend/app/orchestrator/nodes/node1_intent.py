# app/orchestrator/nodes/node1_intent.py
# ═══════════════════════════════════════════════════════════
# Node 1 — Routeur / Planificateur (version LLM-first)
#   - Si un plan existe déjà → retourne state inchangé
#   - Fast paths : chat-only, gibberish
#   - Sinon, le LLM planifie en tenant compte de l'historique
#     et des règles de continuation
# ═══════════════════════════════════════════════════════════

from datetime import date
from langchain_core.messages import HumanMessage, SystemMessage
from app.orchestrator.state import AssistantState, PlanStep
from app.core.groq_client import invoke_with_fallback
from app.a2a.discovery import routing_manifest
from dotenv import load_dotenv
from langsmith import traceable
import json
import re as _re
import unicodedata as _unicodedata

load_dotenv()

# Historique pour le contexte
MAX_HISTORY_MESSAGES = 10
MAX_AI_CHARS_IN_HISTORY = 200

# Fast path tokens chat-only
_CHAT_ONLY_TOKENS = {
    "bonjour", "salut", "hello", "bonsoir", "hi", "coucou",
    "merci", "ok merci", "super merci", "merci beaucoup",
    "au revoir", "bonne journée", "bonne journee", "à bientôt", "a bientot",
    "bonne soirée", "bonne soiree",
}

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
# PROMPT DU PLANNER (inclut une règle de continuation)
# ══════════════════════════════════════════════════════════
PLANNER_SYSTEM_PROMPT = """\
Tu es un planificateur de routage pour un assistant d'entreprise.
Ta seule mission : identifier quel(s) agent(s) doit traiter la demande et leur transmettre le message tel quel.

{agents_section}

══════════════════════════════════════════
PRINCIPE FONDAMENTAL — ROUTAGE PUR, SANS INTERPRÉTATION
══════════════════════════════════════════
Tu n'es PAS un agent d'exécution. Tu es un routeur.
- Tu NE complètes PAS les informations manquantes (date, heure, nom...).
- Tu NE poses PAS de questions à l'utilisateur.
- Tu NE modifies PAS le message utilisateur.
- Tu TRANSMETS le message brut à l'agent compétent : c'est LUI (ReAct agent) qui demandera les précisions.

Exemple CORRECT   : "je veux poser un congé"
→ {{"steps": [{{"step_id": "step1", "agent": "rh", "task": "je veux poser un congé", "depends_on": []}}]}}

Exemple INTERDIT  : step1=chat("quelle est la date") + step2=rh("poser un congé à la date indiquée")
→ FAUX. Ne crée JAMAIS un step "chat" pour injecter la date ou un contexte dans un step métier.

⚠️ ANTI-PATTERNS INTERDITS :
1. Chaîner chat → agent_métier pour obtenir une information (date, heure, etc.)
2. Créer un step "chat" pour une action métier incomplète (congé sans date, réunion sans heure...)
3. Ajouter "à la date indiquée" ou "comme précisé" dans la tâche quand aucune date n'est donnée
4. Utiliser "chat" comme fallback pour un domaine métier non reconnu

La date du jour est déjà injectée dans chaque message envoyé aux agents — inutile de la récupérer via "chat".

══════════════════════════════════════════
AGENTS OFFICIELS — NOMS OBLIGATOIRES
══════════════════════════════════════════
Tu dois TOUJOURS utiliser ces noms exacts pour le champ "agent".
Ces agents sont disponibles même s'ils n'apparaissent pas dans la liste ci-dessus (temporairement indisponibles) :

| Nom      | Utiliser pour                                                    |
|----------|------------------------------------------------------------------|
| rh       | Congés, absences, solde, équipe, compétences                     |
| calendar | Réunions, rendez-vous, agenda, disponibilités                    |
| jira     | Tickets, issues, projets Jira                                    |
| slack    | Envoyer / notifier sur Slack — TOUJOURS "slack", jamais "chat"   |
| crm      | Clients, projets CRM, contacts                                   |
| chat     | UNIQUEMENT : bonjour, merci, au revoir, quelle heure, qui es-tu  |

⚠️ RÈGLES STRICTES sur "chat" :
- "chat" est RÉSERVÉ aux salutations et questions méta (bonjour, merci, quelle date, qui es-tu).
- "chat" ne traite PAS les demandes métier même partielles (congé sans date, réunion sans heure, Slack...).
- Si la demande concerne un domaine métier (congé, réunion, Slack, Jira...) → utilise l'agent métier, jamais "chat".

══════════════════════════════════════════
RÈGLE ABSOLUE — PLANIFIER UNIQUEMENT LA NOUVELLE DEMANDE
══════════════════════════════════════════
⚠️ L'historique est fourni UNIQUEMENT comme contexte pour comprendre la continuation.
Tu dois planifier UNIQUEMENT la dernière demande (marquée "NOUVELLE DEMANDE À PLANIFIER").
Les échanges précédents dans l'historique sont déjà traités — NE LES REPLANIFIE JAMAIS.

Exemple INTERDIT : l'historique montre "refuser le congé de Yassine" et "récupérer les congés"
→ NE PAS créer de steps pour ces actions passées. Planifie SEULEMENT la nouvelle demande.

══════════════════════════════════════════
RÈGLE CONTINUATION DE CONVERSATION
══════════════════════════════════════════
Si l'historique montre qu'un agent a posé une question et que le message actuel est une réponse directe (date, heure, email, chiffre, oui/non) → continue avec le MÊME agent, tâche = message brut.

Exemples :
- Historique : rh : "Pour quelle date ?" / Message : "lundi prochain"
  → {{"steps": [{{"step_id": "step1", "agent": "rh", "task": "lundi prochain", "depends_on": []}}]}}
- Historique : calendar : "À quelle heure ?" / Message : "10h"
  → {{"steps": [{{"step_id": "step1", "agent": "calendar", "task": "10h", "depends_on": []}}]}}
- Historique : rh : "Option 1, 2 ou 3 ?" / Message : "2"
  → {{"steps": [{{"step_id": "step1", "agent": "rh", "task": "2", "depends_on": []}}]}}

══════════════════════════════════════════
RÈGLES DE PLANIFICATION
══════════════════════════════════════════
1. Route chaque action vers son agent dédié selon le tableau ci-dessus.
2. La tâche = reformulation minimale de la demande (ou message brut si c'est une continuation).
3. Utilise "depends_on" si une étape nécessite le résultat d'une autre.
4. Pour l'agent calendar, la vérification de disponibilité est incluse dans la création — ne fais pas deux steps.

══════════════════════════════════════════
EXEMPLES FEW-SHOT
══════════════════════════════════════════
Requête : "je veux poser un congé"
Plan : {{"steps": [{{"step_id": "step1", "agent": "rh", "task": "poser un congé", "depends_on": []}}]}}
→ (pas de date ? RH la demandera lui-même — ne pas créer de step chat avant)

Requête : "crée une réunion"
Plan : {{"steps": [{{"step_id": "step1", "agent": "calendar", "task": "créer une réunion", "depends_on": []}}]}}
→ (pas d'heure ? Calendar la demandera lui-même — ne pas créer de step chat avant)

Requête : "crée une réunion avec mon équipe"
Plan : {{"steps": [{{"step_id": "step1", "agent": "calendar", "task": "créer une réunion avec mon équipe", "depends_on": []}}]}}

Requête : "pose un congé lundi ET crée une réunion mardi"
Plan : {{
  "steps": [
    {{"step_id": "step1", "agent": "rh", "task": "poser un congé lundi", "depends_on": []}},
    {{"step_id": "step2", "agent": "calendar", "task": "créer une réunion mardi", "depends_on": []}}
  ]
}}

Requête : "vérifie mon solde et notifie mon manager sur Slack"
Plan : {{
  "steps": [
    {{"step_id": "step1", "agent": "rh", "task": "vérifier le solde de congés", "depends_on": []}},
    {{"step_id": "step2", "agent": "slack", "task": "notifier le manager du solde de congés", "depends_on": ["step1"]}}
  ]
}}

Requête : "si je pose un congé lundi, préviens mon chef sur Slack"
Plan : {{
  "steps": [
    {{"step_id": "step1", "agent": "rh", "task": "poser un congé lundi", "depends_on": []}},
    {{"step_id": "step2", "agent": "slack", "task": "envoyer un message au chef pour l'informer du congé", "depends_on": ["step1"]}}
  ]
}}

Requête : "bonjour"
Plan : {{"steps": [{{"step_id": "step1", "agent": "chat", "task": "bonjour", "depends_on": []}}]}}

Requête : "quel est mon solde de congés ?"
Plan : {{"steps": [{{"step_id": "step1", "agent": "rh", "task": "vérifier le solde de congés", "depends_on": []}}]}}

Date du jour : {today}
"""


# ══════════════════════════════════════════════════════════
# HELPERS (réutilisés)
# ══════════════════════════════════════════════════════════

def _extract_clean_text(content: str) -> str:
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
    clean = text.lower().strip()
    if not clean:
        return True
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


_ERROR_PREFIXES = ("⚠️", "Erreur lors du traitement", "Une erreur inattendue")

def _build_history_for_llm(trimmed_messages: list) -> str:
    lines = []
    for msg in trimmed_messages[:-1]:
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        content = msg.content if msg.type == "human" else _extract_clean_text(msg.content)
        # Exclure les messages d'erreur système pour ne pas gonfler le contexte
        if msg.type != "human" and any(content.startswith(p) for p in _ERROR_PREFIXES):
            continue
        if msg.type != "human" and len(content) > MAX_AI_CHARS_IN_HISTORY:
            content = content[:MAX_AI_CHARS_IN_HISTORY] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_llm_json(raw: str) -> dict | None:
    """Extrait et parse le JSON de la réponse LLM, en gérant les blocs markdown et les réponses tronquées."""
    content = raw.strip()
    # Gérer les blocs de code markdown
    if "```" in content:
        start_idx = content.find("```")
        end_idx = content.rfind("```")
        if start_idx != -1 and end_idx > start_idx:
            block = content[start_idx+3:end_idx].strip()
            if block.startswith("json"):
                block = block[4:].strip()
            content = block
    # Trouver les accolades
    start = content.find("{")
    end = content.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    json_str = content[start:end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Tentative de récupération si le JSON est tronqué (max_tokens atteint)
        # On tente de récupérer les steps déjà complets avant la troncature
        print(f"⚠️ JSON tronqué détecté, tentative de récupération partielle...")
        steps_start = json_str.find('"steps"')
        if steps_start == -1:
            return None
        arr_start = json_str.find("[", steps_start)
        if arr_start == -1:
            return None
        # Collecter les objets step complets (délimités par { ... })
        steps = []
        i = arr_start + 1
        depth = 0
        step_start_idx = None
        while i < len(json_str):
            c = json_str[i]
            if c == "{":
                if depth == 0:
                    step_start_idx = i
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0 and step_start_idx is not None:
                    step_str = json_str[step_start_idx:i+1]
                    try:
                        step_obj = json.loads(step_str)
                        # Valide qu'on a les champs minimaux
                        if "agent" in step_obj and "task" in step_obj:
                            steps.append(step_obj)
                    except json.JSONDecodeError:
                        pass
                    step_start_idx = None
            i += 1
        if steps:
            print(f"   Récupération partielle : {len(steps)} step(s) extraits")
            return {"steps": steps}
        return None


def _normalize_french(text: str) -> str:
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
    if len(ranked) >= 2:
        best, second = ranked[0][1], ranked[1][1]
        if best > 0 and (best - second) / best < 0.25:
            return None
    return ranked[0][0]


# ══════════════════════════════════════════════════════════
# PLANIFICATION
# ══════════════════════════════════════════════════════════

async def _generate_plan(state: AssistantState) -> list[PlanStep]:
    """Appelle le LLM pour générer un plan structuré, avec gestion de la continuation."""
    manifest = await routing_manifest.build()
    agents_section = manifest.routing_prompt

    all_messages = state["messages"]
    trimmed = (
        all_messages[-MAX_HISTORY_MESSAGES:]
        if len(all_messages) > MAX_HISTORY_MESSAGES
        else all_messages
    )
    history = _build_history_for_llm(trimmed)
    last_message = trimmed[-1].content

    _today = date.today()
    _JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    today_str = f"{_today.strftime('%Y-%m-%d')} ({_JOURS[_today.weekday()]})"

    system_prompt = PLANNER_SYSTEM_PROMPT.format(
        agents_section=agents_section,
        today=today_str
    )
    user_content = (
        f"=== HISTORIQUE (contexte uniquement — NE PAS planifier ces échanges) ===\n"
        f"{history}\n"
        f"=== FIN HISTORIQUE ===\n\n"
        f"=== NOUVELLE DEMANDE À PLANIFIER (UNIQUEMENT CELLE-CI) ===\n"
        f"{last_message}"
    )

    llm_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]
    _PLANNER_MODELS = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"]

    try:
        raw = ""
        for model in _PLANNER_MODELS:
            raw = await invoke_with_fallback(
                model=model,
                messages=llm_messages,
                temperature=0,
                max_tokens=1200,
            )
            print(f"RAW RESPONSE ({model}):", raw)
            if raw and raw.strip():
                break
            print(f"⚠️ Réponse vide avec {model}, essai du modèle suivant…")

        result = _parse_llm_json(raw)
        if result is None:
            raise ValueError("Impossible d'extraire le JSON")
        steps = result.get("steps", [])
        validated = []
        for i, step in enumerate(steps):
            validated.append({
                "step_id": step.get("step_id", f"step{i+1}"),
                "agent": step["agent"],
                "task": step["task"],
                "depends_on": step.get("depends_on", []),
                "status": "pending",
                "result": None
            })
        return validated
    except Exception as e:
        print(f"⚠️ Échec génération plan : {e}")
        # Fallback par mots-clés (dernier recours — un seul agent, sans dépendances)
        last_message_lower = state["messages"][-1].content.lower()
        # Slack détecté en priorité
        slack_keywords = ["slack", "notifie", "notifier", "message à", "préviens", "previens", "envoie à"]
        # Calendar
        cal_keywords = ["réunion", "reunion", "meeting", "agenda", "calendrier", "créneau", "horaire", "rendez-vous"]
        # RH (sans "manager" qui est ambigu)
        rh_keywords = ["congé", "conge", "conges", "solde", "absence", "équipe", "equipe"]

        has_slack = any(kw in last_message_lower for kw in slack_keywords)
        has_cal = any(kw in last_message_lower for kw in cal_keywords)
        has_rh = any(kw in last_message_lower for kw in rh_keywords)

        # Priorité en fallback : slack > calendar > rh
        # (slack est le plus spécifique — si mentionné, c'est intentionnel)
        if has_slack:
            agent = "slack"
        elif has_cal:
            agent = "calendar"
        elif has_rh:
            agent = "rh"
        else:
            agent = "chat"

        return [{
            "step_id": "step1",
            "agent": agent,
            "task": last_message,
            "depends_on": [],
            "status": "pending",
            "result": None
        }]


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
    Routeur / planificateur :
      - Si un plan existe déjà → retourne state inchangé (reprise)
      - Fast paths : chat-only, gibberish (sans LLM)
      - Sinon, le LLM planifie (y compris la continuation via l'historique)
    """
    # Si un plan est déjà en cours (reprise après question), on ne fait rien
    if state.get("plan") is not None:
        print("📌 Plan existant détecté → reprise de l’exécution")
        return state

    # Préparer les données
    manifest = await routing_manifest.build()
    all_messages = state["messages"]
    trimmed = (
        all_messages[-MAX_HISTORY_MESSAGES:]
        if len(all_messages) > MAX_HISTORY_MESSAGES
        else all_messages
    )
    last_message = trimmed[-1].content

    print(f"\n{'='*60}")
    print(f"🔍 NODE 1 — PLANIFICATEUR")
    print(f"{'='*60}")
    print(f"📨 Message : {last_message[:120]}")
    print(f"📚 {len(all_messages)} msgs total → {len(trimmed)} trimmed")

    # ╔══════════════════════════════════════════════════════╗
    # ║  FAST PATH 1 — Chat-only (sans LLM)                 ║
    # ╚══════════════════════════════════════════════════════╝
    if _is_chat_only(last_message):
        plan = [{
            "step_id": "step1",
            "agent": "chat",
            "task": last_message,
            "depends_on": [],
            "status": "pending",
            "result": None
        }]
        print(f"✅ FAST PATH: chat-only → plan simple")
        print(f"{'='*60}\n")
        return {**state, "plan": plan}

    # ╔══════════════════════════════════════════════════════╗
    # ║  FAST PATH 2 — Gibberish (sans LLM)                 ║
    # ╚══════════════════════════════════════════════════════╝
    if _is_gibberish(last_message):
        plan = [{
            "step_id": "step1",
            "agent": "chat",
            "task": last_message,
            "depends_on": [],
            "status": "pending",
            "result": None
        }]
        print(f"🚫 FAST PATH: gibberish → plan simple chat")
        print(f"{'='*60}\n")
        return {**state, "plan": plan}

    # ╔══════════════════════════════════════════════════════╗
    # ║  PRIMARY — Génération du plan via LLM               ║
    # ║  (le LLM gère la continuation grâce à l'historique) ║
    # ╚══════════════════════════════════════════════════════╝
    plan = await _generate_plan(state)
    print(f"✅ Plan généré : {len(plan)} étape(s)")
    for p in plan:
        print(f"   - {p['step_id']}: {p['agent']} → {p['task'][:60]}")
    print(f"{'='*60}\n")
    return {**state, "plan": plan}