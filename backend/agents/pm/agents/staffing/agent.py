# agents/pm/agents/staffing/agent.py
# Phase 8 — Staffing (affectation des stories aux employés)
# STUB — implémentation complète à venir.

from agents.pm.state import PMPipelineState


async def node_staffing(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 8 : affectation des stories aux employés.

    Interroge hris.employees pour récupérer les compétences disponibles.
    Le LLM fait correspondre les besoins de la story (description / acceptance criteria)
    aux compétences employé.

    staffing : { story_id (int) → employee_id (int) }
    employee_id = hris.employees.id
    """
    project_id     = state.get("project_id")
    stories        = state.get("stories", []) or []
    human_feedback = state.get("human_feedback")

    print(f"[staffing] Phase 8 | projet={project_id} | {len(stories)} stories (stub)")

    return {
        "staffing":          {},
        "current_phase":     "staffing",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
