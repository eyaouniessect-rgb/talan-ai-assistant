# agents/pm/agents/refinement/agent.py
# Phase 4 — Raffinement PO ↔ Tech Lead (orchestrateur déterministe, max 3 rounds)

from agents.pm.state.state                         import PMPipelineState
from agents.pm.agents.refinement.service           import run_one_round
from agents.pm.agents.refinement.repository        import save_refined_stories


async def node_refinement(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 4 : raffinement PO ↔ Tech Lead.

    Exécute UNIQUEMENT le Round 1. Les rounds suivants sont déclenchés
    par le PM via POST /refinement/round/apply après validation story par story.
    node_validate() interrompra le graph avec awaiting_round_review=True.
    """
    project_id           = state.get("project_id")
    stories              = state.get("stories", [])
    epics                = state.get("epics", [])
    architecture_details = state.get("architecture_details") if state.get("architecture_detected") else None

    print(f"[refinement] Phase 4 | projet={project_id} | {len(stories)} stories | {len(epics)} epics")

    if not stories:
        return {
            "refined_stories":      [],
            "stories_before_round": [],
            "refinement_rounds":    [],
            "current_round":        0,
            "refinement_consensus": False,
            "current_phase":        "refinement",
            "validation_status":    "pending_human",
            "human_feedback":       None,
            "error":                "Aucune story disponible pour le raffinement.",
        }

    stories_before_round = list(stories)

    try:
        refined_stories, round_data = await run_one_round(
            stories              = stories,
            epics                = epics,
            round_number         = 1,
            architecture_details = architecture_details,
            previous_rounds      = [],   # Round 1 : aucun round précédent
        )
    except Exception as e:
        error_msg = str(e)[:300]
        print(f"[refinement] ERREUR Round 1 : {type(e).__name__}: {error_msg}")
        # Fail-safe : stories originales, PM peut quand même valider
        return {
            "refined_stories":      stories,
            "stories_before_round": stories_before_round,
            "refinement_rounds":    [],
            "current_round":        1,
            "refinement_consensus": False,
            "current_phase":        "refinement",
            "validation_status":    "pending_human",
            "human_feedback":       None,
            "error":                error_msg,
        }

    if project_id:
        await save_refined_stories(project_id, refined_stories)

    return {
        "refined_stories":      refined_stories,
        "stories_before_round": stories_before_round,
        "refinement_rounds":    [round_data],
        "current_round":        1,
        "refinement_consensus": round_data.get("consensus", False),
        "current_phase":        "refinement",
        "validation_status":    "pending_human",
        "human_feedback":       None,
        "error":                None,
    }
