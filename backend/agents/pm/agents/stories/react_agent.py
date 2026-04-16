# agents/pm/agents/stories/react_agent.py
# ═══════════════════════════════════════════════════════════════
# Agent ReAct — Génération de User Stories
#
# Correction de troncature JSON :
#   Les tools NE passent PLUS le JSON entre eux via les arguments.
#   Le LLM passe uniquement epic_idx (un entier).
#   Les résultats intermédiaires sont stockés dans _epic_store[epic_idx].
#
# Flux par epic :
#   1. generate_stories_for_epic(epic_idx)          → stocke dans _epic_store[N]
#   2. estimate_story_points(epic_idx)              → lit + enrichit _epic_store[N]
#   3. generate_acceptance_criteria(epic_idx)       → lit + enrichit _epic_store[N]
#   4. review_coverage(epic_idx)                    → lit _epic_store[N], retourne gaps
#      → si gaps : regenerate_missing(epic_idx, missing_features) puis retour en 2
#   5. epic_done(epic_idx) → marque l'epic terminé  → LLM passe à l'epic suivant
# ═══════════════════════════════════════════════════════════════

import json
import re
import asyncio

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from app.core.groq_client import build_llm

from agents.pm.agents.stories.tools.generate import run_generate_for_epic
from agents.pm.agents.stories.tools.estimate import run_estimate_story_points
from agents.pm.agents.stories.tools.criteria import run_generate_acceptance_criteria
from agents.pm.agents.stories.tools.review   import run_review_coverage

# ──────────────────────────────────────────────────────────────
# État global
# ──────────────────────────────────────────────────────────────
_current_epics:                list[dict]  = []
_current_architecture_details: dict | None = None
_current_human_feedback:       str | None  = None

# Store intermédiaire : epic_idx → stories (enrichies progressivement)
# Le LLM ne passe JAMAIS le JSON complet — il passe juste epic_idx
_epic_store: dict[int, list[dict]] = {}

# Store des résultats de review_coverage par epic_idx
# { epic_idx → { coverage_ok, gaps, scope_creep_issues, quality_issues, suggestions } }
_review_store: dict[int, dict] = {}


# ──────────────────────────────────────────────────────────────
# Queue d'événements SSE
# ──────────────────────────────────────────────────────────────
_story_event_queues: dict[int, asyncio.Queue] = {}


def get_or_create_queue(project_id: int) -> asyncio.Queue:
    if project_id not in _story_event_queues:
        _story_event_queues[project_id] = asyncio.Queue()
    return _story_event_queues[project_id]


def clear_queue(project_id: int) -> None:
    _story_event_queues.pop(project_id, None)


# ──────────────────────────────────────────────────────────────
# TOOLS  (le LLM passe seulement epic_idx — jamais de gros JSON)
# ──────────────────────────────────────────────────────────────

@tool
async def generate_stories_for_epic(epic_idx: int, missing_features: str = "") -> str:
    """
    Génère les User Stories pour l'epic à l'index donné (0, 1, 2…).
    Les stories sont stockées en interne — ne retourne qu'un résumé court.

    Paramètres :
      epic_idx        : index de l'epic dans la liste (obligatoire)
      missing_features: fonctionnalités manquantes séparées par des virgules,
                        à utiliser uniquement si review_coverage a détecté des gaps
    """
    if epic_idx >= len(_current_epics):
        return json.dumps({"error": f"epic_idx {epic_idx} hors limites", "count": 0})

    epic    = _current_epics[epic_idx]
    missing = [f.strip() for f in missing_features.split(",") if f.strip()] if missing_features else None

    stories = await run_generate_for_epic(
        epic                 = epic,
        epic_idx             = epic_idx,
        architecture_details = _current_architecture_details,
        missing_features     = missing,
        human_feedback       = _current_human_feedback,
    )
    _epic_store[epic_idx] = stories
    return json.dumps({"epic_idx": epic_idx, "status": "ok", "count": len(stories)})


@tool
async def estimate_story_points(epic_idx: int) -> str:
    """
    Estime les story points Fibonacci (1,2,3,5,8) pour les stories de l'epic.
    Appeler après generate_stories_for_epic. 13 est INTERDIT.

    Paramètre :
      epic_idx : index de l'epic (même valeur que generate_stories_for_epic)
    """
    stories = _epic_store.get(epic_idx, [])
    if not stories:
        return json.dumps({"error": f"Aucune story en mémoire pour epic {epic_idx}"})

    estimated = await run_estimate_story_points(stories)
    _epic_store[epic_idx] = estimated
    return json.dumps({"epic_idx": epic_idx, "status": "ok", "count": len(estimated)})


@tool
async def generate_acceptance_criteria(epic_idx: int) -> str:
    """
    Génère les critères d'acceptation Gherkin pour les stories de l'epic.
    Appeler après estimate_story_points.

    Paramètre :
      epic_idx : index de l'epic
    """
    stories = _epic_store.get(epic_idx, [])
    if not stories:
        return json.dumps({"error": f"Aucune story en mémoire pour epic {epic_idx}"})

    with_ac = await run_generate_acceptance_criteria(stories)
    _epic_store[epic_idx] = with_ac
    return json.dumps({"epic_idx": epic_idx, "status": "ok", "count": len(with_ac)})


@tool
async def review_coverage(epic_idx: int) -> str:
    """
    Vérifie si les stories couvrent les fonctionnalités majeures de l'epic.
    Appeler après generate_acceptance_criteria.

    Retourne { coverage_ok, gaps, suggestions }.
    Si coverage_ok=false : appelle generate_stories_for_epic(epic_idx, missing_features="gap1, gap2")
                           puis recommence estimate + generate_acceptance_criteria.
    Si coverage_ok=true  : passe à l'epic suivant (epic_idx + 1).

    Paramètre :
      epic_idx : index de l'epic
    """
    if epic_idx >= len(_current_epics):
        return json.dumps({"epic_idx": epic_idx, "coverage_ok": True, "gaps": []})

    stories  = _epic_store.get(epic_idx, [])
    epic     = _current_epics[epic_idx]
    coverage = await run_review_coverage(epic, epic_idx, stories)
    _review_store[epic_idx] = coverage   # persisté pour le frontend
    return json.dumps({"epic_idx": epic_idx, **coverage})


TOOLS = [
    generate_stories_for_epic,
    estimate_story_points,
    generate_acceptance_criteria,
    review_coverage,
]


# ──────────────────────────────────────────────────────────────
# PROMPT SYSTÈME
# ──────────────────────────────────────────────────────────────

def _build_system_prompt(nb_epics: int) -> str:
    return f"""Tu es un orchestrateur Agile expert en génération de User Stories.
Tu dois générer les User Stories pour {nb_epics} epic(s) (indices 0 à {nb_epics - 1}).

══════════════════════════════════════════════════════════════
PROCESSUS POUR CHAQUE EPIC — ordre strict : 0, 1, 2…
══════════════════════════════════════════════════════════════

ÉTAPE 1 → generate_stories_for_epic(epic_idx=N)
ÉTAPE 2 → estimate_story_points(epic_idx=N)
ÉTAPE 3 → generate_acceptance_criteria(epic_idx=N)
ÉTAPE 4 → review_coverage(epic_idx=N)

  Si coverage_ok=false et gaps non vides :
    → generate_stories_for_epic(epic_idx=N, missing_features="gap1, gap2")
    → estimate_story_points(epic_idx=N)
    → generate_acceptance_criteria(epic_idx=N)
    → NE PAS refaire review — passer directement à l'epic suivant

  Si coverage_ok=true → passer à l'epic suivant (N+1)

  Note : review_coverage retourne aussi scope_creep_issues et quality_issues (informatif uniquement).
  Ces champs sont loggés mais ne déclenchent PAS de régénération — le PM les verra lors de la validation.

══════════════════════════════════════════════════════════════
RÈGLES CRITIQUES
══════════════════════════════════════════════════════════════
- Traite les epics DANS L'ORDRE : 0, 1, 2, …
- Chaque outil reçoit UNIQUEMENT epic_idx (pas de JSON, pas d'autre argument)
  sauf generate_stories_for_epic qui peut recevoir missing_features
- Quand TOUS les epics sont traités, réponds : "Génération terminée."
"""


# ──────────────────────────────────────────────────────────────
# EXTRACTION des stories depuis _epic_store
# ──────────────────────────────────────────────────────────────

def _collect_stories_from_store(nb_epics: int) -> list[dict]:
    """Collecte les stories depuis le store interne (plus fiable que les ToolMessages).
    Attache les données de review de chaque epic à chaque story (_review)."""
    all_stories: list[dict] = []
    for epic_idx in range(nb_epics):
        stories = _epic_store.get(epic_idx, [])
        review  = _review_store.get(epic_idx, {})
        for s in stories:
            s["epic_id"] = epic_idx
            # Données de revue au niveau de l'epic — visible dans le frontend
            s["_review"] = {
                "coverage_ok":        review.get("coverage_ok", True),
                "scope_creep_issues": review.get("scope_creep_issues", []),
                "quality_issues":     review.get("quality_issues", []),
                "suggestions":        review.get("suggestions", []),
            }
        all_stories.extend(stories)
        print(f"[react_agent]   Epic {epic_idx}: {len(stories)} stories | review={'ok' if review.get('coverage_ok', True) else 'gaps'}")
    return all_stories


def _extract_stories_from_messages(messages: list) -> list[dict]:
    """Fallback : extraction depuis les ToolMessages si le store est vide."""
    tool_call_map: dict[str, str] = {}
    for msg in messages:
        if type(msg).__name__ == "AIMessage":
            for tc in getattr(msg, "tool_calls", []) or []:
                tool_call_map[tc["id"]] = tc["name"]

    ac_by_epic: dict[int, list[dict]] = {}
    for msg in messages:
        if type(msg).__name__ != "ToolMessage":
            continue
        tc_id     = getattr(msg, "tool_call_id", None)
        tool_name = tool_call_map.get(tc_id, "") if tc_id else getattr(msg, "name", "")

        if tool_name == "generate_acceptance_criteria":
            try:
                data     = json.loads(msg.content)
                epic_idx = int(data.get("epic_idx", 0))
                stories  = data.get("stories", [])
                if stories:
                    ac_by_epic[epic_idx] = stories
            except (json.JSONDecodeError, ValueError, KeyError):
                pass

    all_stories: list[dict] = []
    for epic_idx in sorted(ac_by_epic.keys()):
        for s in ac_by_epic[epic_idx]:
            s["epic_id"] = epic_idx
        all_stories.extend(ac_by_epic[epic_idx])
    return all_stories


# ──────────────────────────────────────────────────────────────
# INTERPRÉTATION DES EVENTS astream_events → SSE
# ──────────────────────────────────────────────────────────────

_TOOL_LABELS = {
    "estimate_story_points":        "Estimation des story points (Fibonacci)",
    "generate_acceptance_criteria": "Génération des critères d'acceptation (Gherkin)",
    "review_coverage":              "Revue de couverture fonctionnelle",
}


async def _handle_astream_event(event: dict, emit) -> None:
    etype = event["event"]

    if etype == "on_tool_start":
        tool_name = event["name"]
        args      = event["data"].get("input", {}) or {}

        if tool_name == "generate_stories_for_epic":
            epic_idx = int(args.get("epic_idx", 0)) if isinstance(args, dict) else 0
            missing  = str(args.get("missing_features", "") or "") if isinstance(args, dict) else ""
            epic_title = _current_epics[epic_idx]["title"] if epic_idx < len(_current_epics) else f"Epic {epic_idx + 1}"

            if missing.strip():
                gaps = [f.strip() for f in missing.split(",") if f.strip()]
                await emit({
                    "type": "retry_start", "epic_idx": epic_idx,
                    "epic_title": epic_title, "missing_features": gaps,
                    "thinking": (
                        f"🔄 Régénération ciblée pour l'epic «\u00a0{epic_title}\u00a0» — "
                        f"couverture des manques : {', '.join(gaps[:3])}{'…' if len(gaps) > 3 else ''}"
                    ),
                })
            else:
                await emit({
                    "type": "epic_start", "epic_idx": epic_idx,
                    "epic_title": epic_title, "nb_epics": len(_current_epics),
                })

        elif tool_name in _TOOL_LABELS:
            epic_idx = int(args.get("epic_idx", 0)) if isinstance(args, dict) else 0
            await emit({
                "type": "tool_start", "epic_idx": epic_idx,
                "tool": tool_name, "label": _TOOL_LABELS[tool_name],
            })

    elif etype == "on_tool_end":
        tool_name = event["name"]
        output    = event["data"].get("output", "") or ""
        # LangGraph astream_events v2 : output est un objet ToolMessage, pas une str
        if hasattr(output, "content"):
            output = output.content or ""

        if tool_name == "review_coverage":
            try:
                data       = json.loads(output)
                epic_idx   = int(data.get("epic_idx", 0))
                epic_title = _current_epics[epic_idx]["title"] if epic_idx < len(_current_epics) else f"Epic {epic_idx + 1}"

                if not data.get("coverage_ok", True) and data.get("gaps"):
                    gaps = data["gaps"]
                    await emit({
                        "type": "gap_detected", "epic_idx": epic_idx,
                        "epic_title": epic_title, "gaps": gaps,
                        "thinking": (
                            f"⚠\ufe0f {len(gaps)} fonctionnalité(s) non couverte(s) "
                            f"dans «\u00a0{epic_title}\u00a0»\u00a0: "
                            f"{', '.join(gaps[:3])}{'…' if len(gaps) > 3 else ''}. "
                            f"Régénération ciblée en cours."
                        ),
                    })
                else:
                    await emit({"type": "coverage_ok", "epic_idx": epic_idx, "epic_title": epic_title})
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        elif tool_name == "generate_acceptance_criteria":
            try:
                data     = json.loads(output)
                epic_idx = int(data.get("epic_idx", 0))
                count    = int(data.get("count", 0))
                await emit({"type": "epic_done", "epic_idx": epic_idx, "stories_count": count})
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    elif etype == "on_chat_model_stream":
        chunk = event["data"].get("chunk")
        if chunk and hasattr(chunk, "content") and chunk.content:
            await emit({"type": "llm_token", "token": chunk.content})


# ──────────────────────────────────────────────────────────────
# MESSAGE HUMAN
# ──────────────────────────────────────────────────────────────

def _build_human_message(epics: list[dict], human_feedback: str | None) -> str:
    epics_summary = "\n".join([
        f"  Epic {i}: {e['title']} (stratégie: {e.get('splitting_strategy', 'by_feature')})"
        for i, e in enumerate(epics)
    ])
    feedback_section = (
        f"\n⚠ FEEDBACK DU PM (à intégrer dans toutes les stories) :\n{human_feedback}\n"
    ) if human_feedback else ""

    return (
        f"Génère les User Stories pour ces {len(epics)} epic(s) :\n\n"
        f"{epics_summary}\n"
        f"{feedback_section}\n"
        f"Traite chaque epic dans l'ordre en utilisant les 4 tools."
    )


# ──────────────────────────────────────────────────────────────
# ENTRÉE PRINCIPALE
# ──────────────────────────────────────────────────────────────

async def run_stories_react_agent(
    epics: list[dict],
    human_feedback: str | None = None,
    architecture_details: dict | None = None,
    project_id: int | None = None,
) -> list[dict]:
    """
    Orchestre la génération des User Stories via create_react_agent + astream_events.
    Les tools ne s'échangent que epic_idx (entier) — jamais de JSON volumineux.
    """
    global _current_epics, _current_architecture_details, _current_human_feedback
    _current_epics                = epics
    _current_architecture_details = architecture_details
    _current_human_feedback       = human_feedback
    _epic_store.clear()
    _review_store.clear()

    queue = get_or_create_queue(project_id) if project_id else None

    async def emit(evt: dict) -> None:
        if queue:
            await queue.put(evt)

    print(f"\n[react_agent] Démarrage — {len(epics)} epic(s) | project_id={project_id}")

    llm = build_llm(
        model       = "openai/gpt-oss-120b",
        temperature = 0,
        max_tokens  = 2048,
    )
    agent = create_react_agent(
        model  = llm,
        tools  = TOOLS,
        prompt = _build_system_prompt(len(epics)),
    )

    human_msg   = _build_human_message(epics, human_feedback)
    result_msgs = []

    try:
        async for event in agent.astream_events(
            {"messages": [HumanMessage(content=human_msg)]},
            config={"recursion_limit": 200},  # 5 epics × 4 tools × 2 steps = ~40 min
            version="v2",
        ):
            await _handle_astream_event(event, emit)

            if event["event"] == "on_chain_end":
                output = event["data"].get("output", {})
                if isinstance(output, dict) and "messages" in output:
                    result_msgs = output["messages"]

    except Exception as e:
        print(f"[react_agent] ❌ Erreur : {type(e).__name__}: {e}")
        # On collecte quand même les stories partielles déjà dans le store
        partial = _collect_stories_from_store(len(epics))
        if partial:
            print(f"[react_agent] ⚠ Récupération partielle : {len(partial)} stories sauvegardées malgré l'erreur")
            if queue:
                await queue.put({"type": "error", "message": str(e)})
            return partial
        if queue:
            await queue.put({"type": "error", "message": str(e)})
        raise

    # Log du cycle
    print(f"[react_agent] ─── Cycle ReAct ───")
    for msg in result_msgs:
        mtype = type(msg).__name__
        if mtype == "AIMessage":
            if msg.content:
                print(f"  🤔 Think : {str(msg.content)[:200]}")
            for tc in getattr(msg, "tool_calls", []) or []:
                print(f"  🔧 Act   : {tc['name']}({str(tc.get('args', {}))[:100]})")
        elif mtype == "ToolMessage":
            print(f"  👁  Obs  : {str(msg.content)[:100]}")
    print(f"[react_agent] ────────────────────")

    # Collecte prioritaire depuis le store interne (plus fiable)
    all_stories = _collect_stories_from_store(len(epics))

    # Fallback si le store est vide (edge case : le LLM n'a pas appelé les tools)
    if not all_stories:
        print("[react_agent] ⚠ Store vide → fallback ToolMessages")
        all_stories = _extract_stories_from_messages(result_msgs)

    print(f"[react_agent] ✓ {len(all_stories)} stories extraites")

    if queue:
        await queue.put({
            "type": "done",
            "total_stories": len(all_stories),
            "nb_epics":      len(epics),
        })
        asyncio.get_event_loop().call_later(30, lambda: clear_queue(project_id))

    return all_stories
