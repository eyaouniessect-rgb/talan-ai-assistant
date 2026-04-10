# agents/pm/agents/refinement/agent.py
# Phase 4 — Raffinement PO ↔ Tech Lead (multi-agent, max 3 rounds)
# STUB — implémentation complète à venir.

from agents.pm.state import PMPipelineState


async def node_refinement(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 4 : raffinement PO ↔ Tech Lead.

    Pattern multi-agent :
      - Agent PO     : vérifie la valeur métier, les critères d'acceptation
      - Agent TL     : vérifie la faisabilité technique, les story points
      - Agent Arbitre: détecte le consensus et valide les stories finales

    Max 3 rounds de débat. Si consensus atteint avant 3 rounds → arrêt anticipé.
    """
    project_id     = state.get("project_id")
    stories        = state.get("stories", [])
    human_feedback = state.get("human_feedback")

    print(f"[refinement] Phase 4 | projet={project_id} | {len(stories)} stories (stub)")

    # STUB : passe les stories sans modification
    return {
        "refined_stories":   stories,
        "refinement_rounds": [],
        "current_phase":     "refinement",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
