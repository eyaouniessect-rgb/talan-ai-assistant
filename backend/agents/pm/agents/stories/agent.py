# agents/pm/agents/stories/agent.py
# Phase 3 — Génération des User Stories + acceptance_criteria
#
# Cas 1 — Première génération (human_feedback=None) :
#   → generate_stories() pour tous les epics
#
# Cas 2 — Rejet global (human_feedback set, targeted_story_ids vide) :
#   → generate_stories() pour tous les epics avec le feedback
#
# Cas 3 — Rejet ciblé (targeted_story_ids non vide) :
#   → improve_targeted_stories() pour les stories cochées seulement
#   → UPDATE en base (db_id inchangé), les autres stories restent intactes

from agents.pm.state import PMPipelineState
from agents.pm.agents.stories.service    import generate_stories
from agents.pm.agents.stories.repository import (
    save_stories,
    get_stories_by_ids,
    get_all_stories_as_dicts,
    update_story,
)
from agents.pm.agents.stories.tools.targeted_regen import improve_targeted_stories


async def node_stories(state: PMPipelineState) -> dict:
    """Noeud LangGraph — Phase 3 : génération des User Stories."""
    project_id            = state.get("project_id")
    epics                 = state.get("epics", [])
    human_feedback        = state.get("human_feedback")
    targeted_story_ids    = state.get("targeted_story_ids") or []
    architecture_detected = state.get("architecture_detected", False)
    architecture_details  = state.get("architecture_details") if architecture_detected else None
    business_actors       = state.get("business_actors") or []

    print(
        f"[stories] Phase 3 | projet={project_id} | {len(epics)} epics"
        f" | feedback={'oui' if human_feedback else 'non'}"
        f" | cible={len(targeted_story_ids)} stories"
    )

    if not epics:
        return {"error": "Aucun epic disponible pour generer les stories.", "current_phase": "stories"}

    # CAS 3 : rejet cible — ameliorer uniquement les stories selectionnees
    if human_feedback and targeted_story_ids:
        print(f"[stories] Rejet cible -> amelioration de {len(targeted_story_ids)} stories")
        try:
            stories = await _partial_regen(project_id, targeted_story_ids, human_feedback)
        except Exception as e:
            print(f"[stories] ERREUR partial regen : {type(e).__name__}: {str(e)[:200]}")
            stories = await get_all_stories_as_dicts(project_id) if project_id else []

        return _done(stories)

    # CAS 1 & 2 : generation complete (premiere fois ou rejet global)
    try:
        stories = await generate_stories(
            epics, human_feedback, architecture_details,
            project_id=project_id, business_actors=business_actors,
        )
    except Exception as e:
        error_msg = str(e)[:300]
        print(f"[stories] ERREUR : {type(e).__name__}: {error_msg}")
        return {
            "stories": [], "error": error_msg, "current_phase": "stories",
            "validation_status": "pending_human", "human_feedback": None,
            "targeted_story_ids": None, "targeted_epic_ids": None,
        }

    print(f"[stories] {len(stories)} stories generees")

    if project_id:
        await save_stories(project_id, stories)

    return _done(stories)


def _done(stories: list[dict]) -> dict:
    return {
        "stories":            stories,
        "current_phase":      "stories",
        "validation_status":  "pending_human",
        "human_feedback":     None,
        "targeted_story_ids": None,
        "targeted_epic_ids":  None,
        "error":              None,
    }


async def _partial_regen(
    project_id: int,
    targeted_story_ids: list[int],
    feedback: str,
) -> list[dict]:
    """
    Charge les stories ciblees, les ameliore via LLM, met a jour en DB,
    puis retourne la liste complete des stories du projet.
    """
    stories_to_fix = await get_stories_by_ids(targeted_story_ids)
    if not stories_to_fix:
        print("[stories] Aucune story trouvee pour les IDs cibles -> skip")
        return await get_all_stories_as_dicts(project_id)

    print(f"[stories] A ameliorer : {[s['title'][:40] for s in stories_to_fix]}")

    improved = await improve_targeted_stories(stories_to_fix, feedback)

    for s in improved:
        await update_story(s["db_id"], {
            "title":               s["title"],
            "description":         s["description"],
            "story_points":        s["story_points"],
            "acceptance_criteria": s["acceptance_criteria"],
        })
        print(f"[stories] Story {s['db_id']} mise a jour")

    return await get_all_stories_as_dicts(project_id)
