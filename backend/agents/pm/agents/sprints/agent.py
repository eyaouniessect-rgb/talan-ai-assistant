# agents/pm/agents/sprints/agent.py
# Phase 10 — Sprint Planning
# STUB — implémentation complète à venir.

from agents.pm.state import PMPipelineState


async def node_sprints(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 10 : sprint planning.

    Le LLM répartit les stories/tasks en sprints en tenant compte :
      - Du chemin critique (tasks critiques → sprints précoces)
      - Des priorités MoSCoW (must → sprint 1)
      - D'une vélocité d'équipe estimée

    Structure d'un sprint :
    {
      "name": str, "goal": str, "start_date": str (ISO), "end_date": str (ISO),
      "story_ids": [int], "task_ids": [int]
    }
    """
    project_id     = state.get("project_id")
    tasks          = state.get("tasks", [])
    critical_path  = state.get("critical_path", [])
    priorities     = state.get("priorities", [])
    human_feedback = state.get("human_feedback")

    print(f"[sprints] Phase 10 | projet={project_id} | {len(tasks)} tasks (stub)")

    return {
        "sprints":           [],
        "current_phase":     "sprints",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
