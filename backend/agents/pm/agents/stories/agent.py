# agents/pm/agents/stories/agent.py
# Phase 3 — Génération des User Stories + acceptance_criteria

from agents.pm.state import PMPipelineState
from agents.pm.agents.stories.service    import generate_stories
from agents.pm.agents.stories.repository import save_stories


async def node_stories(state: PMPipelineState) -> dict:
    """Noeud LangGraph — Phase 3 : génération des User Stories."""
    project_id           = state.get("project_id")
    epics                = state.get("epics", [])
    human_feedback       = state.get("human_feedback")
    architecture_detected= state.get("architecture_detected", False)
    architecture_details = state.get("architecture_details") if architecture_detected else None

    print(f"[stories] Phase 3 | projet={project_id} | {len(epics)} epics"
          f" | architecture={'oui' if architecture_details else 'non'}")

    if not epics:
        return {"error": "Aucun epic disponible pour générer les stories.", "current_phase": "stories"}

    try:
        stories = await generate_stories(epics, human_feedback, architecture_details,
                                         project_id=project_id)
    except Exception as e:
        error_msg = str(e)[:300]
        print(f"[stories] ERREUR : {type(e).__name__}: {error_msg}")
        return {"stories": [], "error": error_msg, "current_phase": "stories",
                "validation_status": "pending_human", "human_feedback": None}

    print(f"[stories] {len(stories)} stories générées")

    if project_id:
        await save_stories(project_id, stories)

    return {
        "stories":           stories,
        "current_phase":     "stories",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
