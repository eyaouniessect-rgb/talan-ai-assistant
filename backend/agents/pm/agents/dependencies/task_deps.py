# agents/pm/agents/dependencies/task_deps.py
# Phase 8 — Dépendances entre Tasks
# STUB — implémentation complète à venir.

from agents.pm.state import PMPipelineState


async def node_task_deps(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 8 : analyse des dépendances entre tasks.

    Structure : [{"task_id": int, "depends_on_id": int}]
    Utilisé en phase 9 par l'algorithme CPM.
    """
    project_id     = state.get("project_id")
    tasks          = state.get("tasks", [])
    human_feedback = state.get("human_feedback")

    print(f"[task_deps] Phase 8 | projet={project_id} | {len(tasks)} tasks (stub)")

    return {
        "task_dependencies": [],
        "current_phase":     "task_deps",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
