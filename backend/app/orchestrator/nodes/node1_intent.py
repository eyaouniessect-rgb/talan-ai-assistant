# app/orchestrator/nodes/node1_intent.py
# ═══════════════════════════════════════════════════════════
# Node 1 — Routeur / Planificateur (version LLM-first)
#
# Responsabilités :
#   1. Si un plan existe déjà → retourne state inchangé (reprise après question)
#   2. Fast path chat-only   → plan direct vers agent "chat" sans LLM
#   3. Fast path gibberish   → idem
#   4. Sinon                 → LLM planifie via PLANNER_SYSTEM_PROMPT
#      (la continuation de conversation est gérée via l'historique injecté)
#
# Utilitaires importés depuis orchestrator/utils/ :
#   - _is_chat_only, _is_gibberish : classification rapide du message
#   - _build_history_for_llm       : formatage historique pour le prompt LLM
#   - _keyword_fallback            : routage de secours si le LLM échoue
#   - _parse_llm_json              : parsing robuste de la réponse JSON du LLM
# ═══════════════════════════════════════════════════════════

from datetime import date
from langchain_core.messages import HumanMessage, SystemMessage
from app.orchestrator.state import AssistantState, PlanStep
from app.core.groq_client import invoke_with_fallback
from app.a2a.discovery import routing_manifest
from dotenv import load_dotenv
from langsmith import traceable

from app.orchestrator.utils import (
    _is_chat_only,
    _is_gibberish,
    _build_history_for_llm,
    _keyword_fallback,
    _parse_llm_json,
    AGENT_KEYWORD_MAP,
)

load_dotenv()

# ─────────────────────────────────────────────
# Paramètres de l'historique
# ─────────────────────────────────────────────

MAX_HISTORY_MESSAGES = 15    # Nombre max de messages conservés pour le contexte LLM
MAX_AI_CHARS_IN_HISTORY = 200 # Longueur max d'une réponse IA dans l'historique

# Modèles LLM essayés dans l'ordre pour la planification
_PLANNER_MODELS = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"]


# ─────────────────────────────────────────────
# Verbes d'action (utilisés pour la détection heuristique)
# ─────────────────────────────────────────────

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
# PROMPT DU PLANNER
# ══════════════════════════════════════════════════════════
# Règles fondamentales :
#   - Routage PUR : ne jamais interpréter ou compléter le message
#   - Jamais de step "chat" avant un step métier (anti-pattern chaînage)
#   - Continuation : si l'historique montre une question agent → même agent
#   - Planifier UNIQUEMENT la dernière demande (pas les échanges passés)

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
# GÉNÉRATION DU PLAN VIA LLM
# ══════════════════════════════════════════════════════════

async def _generate_plan(state: AssistantState) -> list[PlanStep]:
    """
    Appelle le LLM pour générer un plan structuré, avec gestion de la continuation.
    En cas d'échec, bascule sur _keyword_fallback (AGENT_KEYWORD_MAP).
    """
    manifest = await routing_manifest.build()
    agents_section = manifest.routing_prompt

    # ── Préparation de l'historique ───────────────────────────
    all_messages = state["messages"]
    trimmed = (
        all_messages[-MAX_HISTORY_MESSAGES:]
        if len(all_messages) > MAX_HISTORY_MESSAGES
        else all_messages
    )
    history = _build_history_for_llm(trimmed, max_ai_chars=MAX_AI_CHARS_IN_HISTORY)
    last_message = trimmed[-1].content

    # ── Formatage de la date courante ─────────────────────────
    _today = date.today()
    _JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    today_str = f"{_today.strftime('%Y-%m-%d')} ({_JOURS[_today.weekday()]})"

    # ── Appel LLM (essai en cascade sur _PLANNER_MODELS) ─────
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
        HumanMessage(content=user_content),
    ]

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
            print(f"Reponse vide avec {model}, essai du modele suivant...")

        result = _parse_llm_json(raw)
        if result is None:
            raise ValueError("Impossible d'extraire le JSON de la reponse LLM")

        # ── Validation et normalisation des steps ─────────────
        steps = result.get("steps", [])
        validated: list[PlanStep] = []
        for i, step in enumerate(steps):
            validated.append({
                "step_id":    step.get("step_id", f"step{i+1}"),
                "agent":      step["agent"],
                "task":       step["task"],
                "depends_on": step.get("depends_on", []),
                "status":     "pending",
                "result":     None,
            })
        return validated

    except Exception as e:
        print(f"Echec generation plan : {e}")

        # ── Fallback mots-clés (dernier recours) ──────────────
        # Retourne un plan mono-step en utilisant AGENT_KEYWORD_MAP
        agent = _keyword_fallback(last_message, AGENT_KEYWORD_MAP) or "chat"
        return [{
            "step_id":    "step1",
            "agent":      agent,
            "task":       last_message,
            "depends_on": [],
            "status":     "pending",
            "result":     None,
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
      - Si un plan est déjà en cours (reprise après question) → state inchangé
      - Fast path chat-only  → plan direct sans appel LLM
      - Fast path gibberish  → plan direct sans appel LLM
      - Sinon               → génération du plan via LLM (_generate_plan)
    """
    # ── Reprise après question de l'agent ─────────────────────
    if state.get("plan") is not None:
        print("Plan existant detecte → reprise de l'execution")
        return state

    all_messages = state["messages"]
    trimmed = (
        all_messages[-MAX_HISTORY_MESSAGES:]
        if len(all_messages) > MAX_HISTORY_MESSAGES
        else all_messages
    )
    last_message = trimmed[-1].content

    print(f"\n{'='*60}")
    print(f"NODE 1 — PLANIFICATEUR")
    print(f"{'='*60}")
    print(f"Message : {last_message[:120]}")
    print(f"{len(all_messages)} msgs total → {len(trimmed)} trimmed")

    # ╔══════════════════════════════════════════════════════╗
    # ║  FAST PATH 1 — Chat-only (salutation / politesse)   ║
    # ╚══════════════════════════════════════════════════════╝
    if _is_chat_only(last_message):
        plan = [{
            "step_id": "step1", "agent": "chat", "task": last_message,
            "depends_on": [], "status": "pending", "result": None,
        }]
        print("FAST PATH: chat-only → plan simple")
        print(f"{'='*60}\n")
        return {**state, "plan": plan}

    # ╔══════════════════════════════════════════════════════╗
    # ║  FAST PATH 2 — Gibberish (message sans sens)        ║
    # ╚══════════════════════════════════════════════════════╝
    if _is_gibberish(last_message):
        plan = [{
            "step_id": "step1", "agent": "chat", "task": last_message,
            "depends_on": [], "status": "pending", "result": None,
        }]
        print("FAST PATH: gibberish → plan simple chat")
        print(f"{'='*60}\n")
        return {**state, "plan": plan}

    # ╔══════════════════════════════════════════════════════╗
    # ║  PRIMARY — Génération du plan via LLM               ║
    # ║  (continuation gérée via l'historique injecté)      ║
    # ╚══════════════════════════════════════════════════════╝
    plan = await _generate_plan(state)
    print(f"Plan genere : {len(plan)} etape(s)")
    for p in plan:
        print(f"   - {p['step_id']}: {p['agent']} → {p['task'][:60]}")
    print(f"{'='*60}\n")
    return {**state, "plan": plan}
