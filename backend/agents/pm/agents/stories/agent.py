# agents/pm/agents/stories/agent.py
# Phase 3 — Génération des User Stories + acceptance_criteria

from agents.pm.state import PMPipelineState
from agents.pm.agents.stories.service    import generate_stories
from agents.pm.agents.stories.repository import save_stories


async def node_stories(state: PMPipelineState) -> dict:
    """Noeud LangGraph — Phase 3 : génération des User Stories."""
    project_id     = state.get("project_id")
    epics          = state.get("epics", [])
    human_feedback = state.get("human_feedback")

    print(f"[stories] Phase 3 | projet={project_id} | {len(epics)} epics")

    if not epics:
        return {"error": "Aucun epic disponible pour générer les stories.", "current_phase": "stories"}

    try:
        stories = await generate_stories(epics, human_feedback)
    except ValueError as e:
        return {"error": str(e), "current_phase": "stories"}

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
