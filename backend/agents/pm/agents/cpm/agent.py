# agents/pm/agents/cpm/agent.py
# Phase 9 — Critical Path Method (CPM)
# STUB — implémentation complète à venir (algorithme déterministe, pas de LLM).

from agents.pm.state import PMPipelineState


async def node_cpm(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 9 : calcul du chemin critique (CPM).

    Algorithme déterministe (pas de LLM) :
      1. Construire le graphe orienté acyclique des tasks
      2. Calculer ES (Earliest Start) par forward pass
      3. Calculer LS (Latest Start) par backward pass
      4. slack = LS - ES ; is_critical = (slack == 0)

    cpm_result : { task_idx → { ES, LS, slack, is_critical } }
    critical_path : [task_idx, ...] avec slack == 0
    """
    project_id      = state.get("project_id")
    tasks           = state.get("tasks", [])
    task_deps       = state.get("task_dependencies", [])
    human_feedback  = state.get("human_feedback")

    print(f"[cpm] Phase 9 | projet={project_id} | {len(tasks)} tasks (stub)")

    return {
        "cpm_result":        {},
        "critical_path":     [],
        "current_phase":     "cpm",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
