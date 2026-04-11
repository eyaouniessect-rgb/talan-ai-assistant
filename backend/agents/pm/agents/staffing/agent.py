# agents/pm/agents/staffing/agent.py
# Phase 11 — Staffing (affectation des tasks aux employés)
# STUB — implémentation complète à venir.

from agents.pm.state import PMPipelineState


async def node_staffing(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 11 : affectation des tasks aux employés.

    Interroge hris.employees pour récupérer les compétences disponibles.
    Le LLM fait correspondre task_type ↔ compétences employé.

    staffing : { task_idx (int) → employee_id (int) }
    employee_id = hris.employees.id
    """
    project_id     = state.get("project_id")
    tasks          = state.get("tasks", [])
    human_feedback = state.get("human_feedback")

    print(f"[staffing] Phase 11 | projet={project_id} | {len(tasks)} tasks (stub)")

    return {
        "staffing":          {},
        "current_phase":     "staffing",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
