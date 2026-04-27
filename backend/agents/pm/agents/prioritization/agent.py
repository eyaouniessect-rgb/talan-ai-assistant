# agents/pm/agents/prioritization/agent.py
# Phase 6 — Priorisation MoSCoW
# STUB — implémentation complète à venir.

from agents.pm.state import PMPipelineState


async def node_prioritization(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 6 : priorisation MoSCoW.

    Le LLM évalue chaque story selon :
      - moscow      : "must" | "should" | "could" | "wont"
      - value_score : valeur métier estimée (0.0 → 10.0)
      - final_rank  : classement global (1 = plus prioritaire)

    Structure : [{"story_id": int, "moscow": str, "value_score": float, "final_rank": int}]
    """
    project_id     = state.get("project_id")
    stories        = state.get("stories", [])
    human_feedback = state.get("human_feedback")

    print(f"[prioritization] Phase 6 | projet={project_id} | {len(stories)} stories (stub)")

    return {
        "priorities":        [],
        "current_phase":     "prioritization",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
