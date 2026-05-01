# agents/pm/agents/sprints/agent.py
# Phase 7 — Sprint Planning sur les user stories.
# STUB — implémentation complète à venir.

from agents.pm.state import PMPipelineState


async def node_sprints(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 7 : sprint planning.

    Le LLM répartit les stories en sprints en tenant compte :
      - Du chemin critique (stories critiques → sprints précoces)
      - Des priorités MoSCoW (must → sprint 1)
      - D'une vélocité d'équipe estimée (en story points par sprint)

    Structure d'un sprint :
    {
      "name": str, "goal": str, "start_date": str (ISO), "end_date": str (ISO),
      "story_ids": [int]
    }
    """
    project_id     = state.get("project_id")
    stories        = state.get("stories", []) or []
    critical_path  = state.get("critical_path", []) or []
    priorities     = state.get("priorities", []) or []
    human_feedback = state.get("human_feedback")

    print(f"[sprints] Phase 7 | projet={project_id} | {len(stories)} stories (stub)")

    return {
        "sprints":           [],
        "current_phase":     "sprints",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
