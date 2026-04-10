# agents/pm/agents/tasks/agent.py
# Phase 7 — Décomposition en Tasks techniques
# STUB — implémentation complète à venir.

from agents.pm.state import PMPipelineState


async def node_tasks(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 7 : décomposition des stories en tasks.

    Pour chaque story, le LLM génère les tasks de développement :
      - title, description, duration_days
      - task_type : "frontend"|"backend"|"design"|"devops"|"qa"|"other"

    Structure : [{"story_id": int, "title": str, "description": str,
                  "duration_days": int, "task_type": str}]
    """
    project_id     = state.get("project_id")
    refined_stories = state.get("refined_stories", [])
    stories        = refined_stories or state.get("stories", [])
    human_feedback = state.get("human_feedback")

    print(f"[tasks] Phase 7 | projet={project_id} | {len(stories)} stories (stub)")

    return {
        "tasks":             [],
        "current_phase":     "tasks",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
