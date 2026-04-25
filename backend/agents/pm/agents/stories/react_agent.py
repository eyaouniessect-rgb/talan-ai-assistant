# agents/pm/agents/stories/react_agent.py
# ═══════════════════════════════════════════════════════════════
# Orchestrateur déterministe — Génération de User Stories
#
# Séquence par epic (100% déterministe) :
#   1. run_generate_for_epic()  → stories complètes (title + description + SP + AC)
#   2. run_review_coverage()    → audit couverture
#      Si gaps → retry unique :
#        run_generate_for_epic(missing_features=gaps)
#
# Epics traités EN PARALLÈLE via asyncio.gather, avec un Semaphore
# limitant à MAX_CONCURRENT_EPICS epics simultanés pour éviter le
# rate limiting API (réponses vides "No message content").
#
# Appels LLM : 2 par epic (generate + review)
# Temps total ≈ ceil(nb_epics / MAX_CONCURRENT) × temps_1_epic
# ═══════════════════════════════════════════════════════════════

import asyncio

from agents.pm.agents.stories.tools.generate import run_generate_for_epic
from agents.pm.agents.stories.tools.review   import run_review_coverage

# Max epics traités en parallèle — évite le rate limiting API (réponses vides)
# 3 = bon compromis : 3× plus rapide que séquentiel, sans saturer l'API
MAX_CONCURRENT_EPICS = 3

_current_epics:                list[dict]  = []
_current_architecture_details: dict | None = None
_current_human_feedback:       str | None  = None

_epic_store:   dict[int, list[dict]] = {}
_review_store: dict[int, dict]       = {}

_story_event_queues: dict[int, asyncio.Queue] = {}


def get_or_create_queue(project_id: int) -> asyncio.Queue:
    if project_id not in _story_event_queues:
        _story_event_queues[project_id] = asyncio.Queue()
    return _story_event_queues[project_id]


def clear_queue(project_id: int) -> None:
    _story_event_queues.pop(project_id, None)


def _collect_stories_from_store(nb_epics: int) -> list[dict]:
    all_stories: list[dict] = []
    for epic_idx in range(nb_epics):
        stories = _epic_store.get(epic_idx, [])
        review  = _review_store.get(epic_idx, {})
        for s in stories:
            s["epic_id"] = epic_idx
            s["_review"] = {
                "coverage_ok":        review.get("coverage_ok", True),
                "scope_creep_issues": review.get("scope_creep_issues", []),
                "quality_issues":     review.get("quality_issues", []),
                "suggestions":        review.get("suggestions", []),
            }
        all_stories.extend(stories)
        print(f"[react_agent]   Epic {epic_idx}: {len(stories)} stories | review={'ok' if review.get('coverage_ok', True) else 'gaps'}")
    return all_stories


def _gaps_display(gaps: list, n: int = 3) -> str:
    """Formate une liste de gaps (strings ou dicts) pour l'affichage."""
    strs = [g if isinstance(g, str) else str(g) for g in gaps]
    return ", ".join(strs[:n]) + ("..." if len(strs) > n else "")


async def _process_epic(epic_idx: int, epic: dict, emit) -> None:
    """
    Pipeline par epic : generate_all -> review -> [retry si gaps].
    2 appels LLM au lieu de 4.
    """
    epic_title = epic.get("title", f"Epic {epic_idx + 1}")

    # 1. GENERATION COMPLETE (title + description + SP + AC)
    await emit({
        "type":       "epic_start",
        "epic_idx":   epic_idx,
        "epic_title": epic_title,
        "nb_epics":   len(_current_epics),
    })

    try:
        stories = await run_generate_for_epic(
            epic                 = epic,
            epic_idx             = epic_idx,
            architecture_details = _current_architecture_details,
            missing_features     = None,
            human_feedback       = _current_human_feedback,
        )
    except Exception as e:
        print(f"[orchestrator] generate failed epic {epic_idx} : {e}")
        await emit({"type": "error", "epic_idx": epic_idx, "message": f"Generation echouee : {e}"})
        return

    _epic_store[epic_idx] = stories

    # 2. REVUE DE COUVERTURE
    await emit({
        "type":     "tool_start",
        "epic_idx": epic_idx,
        "tool":     "review_coverage",
        "label":    "Revue de couverture fonctionnelle",
    })
    try:
        review = await run_review_coverage(epic, epic_idx, stories)
    except Exception as e:
        print(f"[orchestrator] review failed epic {epic_idx} : {e} -> coverage_ok=True fail-safe")
        review = {"coverage_ok": True, "gaps": [], "scope_creep_issues": [], "quality_issues": [], "suggestions": []}
    _review_store[epic_idx] = review

    # 3. RETRY UNIQUE SI GAPS
    if not review.get("coverage_ok", True) and review.get("gaps"):
        # Normalise en strings pour eviter le crash si le LLM retourne des dicts
        gaps      = [g if isinstance(g, str) else str(g) for g in review["gaps"]]
        gaps_disp = _gaps_display(gaps)
        await emit({
            "type":       "gap_detected",
            "epic_idx":   epic_idx,
            "epic_title": epic_title,
            "gaps":       gaps,
            "thinking":   f"Gaps detectes dans {epic_title!r} : {gaps_disp}. Regeneration ciblee.",
        })
        await emit({
            "type":             "retry_start",
            "epic_idx":         epic_idx,
            "epic_title":       epic_title,
            "missing_features": gaps,
            "thinking":         f"Regeneration ciblee pour {epic_title!r} — manques : {gaps_disp}",
        })

        try:
            stories = await run_generate_for_epic(
                epic                 = epic,
                epic_idx             = epic_idx,
                architecture_details = _current_architecture_details,
                missing_features     = gaps,
                human_feedback       = _current_human_feedback,
            )
            _epic_store[epic_idx] = stories
        except Exception as e:
            print(f"[orchestrator] retry generate failed : {e} — on garde le premier jet")
    else:
        await emit({"type": "coverage_ok", "epic_idx": epic_idx, "epic_title": epic_title})

    await emit({
        "type":          "epic_done",
        "epic_idx":      epic_idx,
        "stories_count": len(_epic_store.get(epic_idx, [])),
    })


async def run_stories_react_agent(
    epics: list[dict],
    human_feedback: str | None = None,
    architecture_details: dict | None = None,
    project_id: int | None = None,
) -> list[dict]:
    """
    Génère les User Stories de manière déterministe.

    Tous les epics sont traités EN PARALLÈLE (asyncio.gather).
    Chaque epic fait 2 appels LLM : generate_all + review_coverage.

    Temps total ≈ max(temps d'un epic) — indépendant du nombre d'epics.
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

    print(f"\n[orchestrator] {len(epics)} epic(s) | parallelisme={MAX_CONCURRENT_EPICS} | project_id={project_id}")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EPICS)

    async def _safe_process(epic_idx: int, epic: dict) -> None:
        async with semaphore:
            try:
                await _process_epic(epic_idx, epic, emit)
            except Exception as e:
                print(f"[orchestrator] epic {epic_idx} exception inattendue : {e}")
                await emit({"type": "error", "epic_idx": epic_idx, "message": str(e)})

    await asyncio.gather(*[_safe_process(i, e) for i, e in enumerate(epics)])

    all_stories = _collect_stories_from_store(len(epics))
    print(f"[orchestrator] {len(all_stories)} stories generees sur {len(epics)} epics")

    if queue:
        await queue.put({
            "type":          "done",
            "total_stories": len(all_stories),
            "nb_epics":      len(epics),
        })
        try:
            asyncio.get_event_loop().call_later(30, lambda: clear_queue(project_id))
        except RuntimeError:
            clear_queue(project_id)

    return all_stories
