# agents/pm/agents/epics/agent.py
# ═══════════════════════════════════════════════════════════════
# Agent Epics — Phase 2 du pipeline PM
#
# Responsabilités :
#   1. Appelle le LLM pour générer les epics depuis le CDC
#   2. Valide et normalise la réponse JSON
#   3. Persiste les epics dans pm.epics (supprime + reinsère)
#   4. Retourne les epics dans le state LangGraph
#      → node_validate prend le relais pour la validation PM
#
# Si human_feedback est présent dans le state, la phase a été
# rejetée par le PM : le feedback est injecté dans le prompt
# pour que le LLM corrige ses epics.
# ═══════════════════════════════════════════════════════════════

from agents.pm.state import PMPipelineState
from agents.pm.agents.epics.service    import generate_epics
from agents.pm.agents.epics.repository import save_epics


async def node_epics(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 2 : génération des Epics.
    Appelle le LLM, persiste en base, retourne epics dans le state.
    """
    project_id     = state.get("project_id")
    cdc_text       = state.get("cdc_text", "")
    human_feedback = state.get("human_feedback")

    print(f"[epics] Phase 2 | projet={project_id} | feedback={'oui' if human_feedback else 'non'}")

    if not cdc_text:
        return {"error": "cdc_text vide — phase extraction non terminée.", "current_phase": "epics"}

    # ── 1. Génération LLM ────────────────────────────────────
    try:
        epics = await generate_epics(cdc_text, human_feedback)
    except Exception as e:
        error_msg = str(e)
        print(f"[epics] ERREUR : {type(e).__name__}: {error_msg[:200]}")
        return {"epics": [], "error": error_msg, "current_phase": "epics",
                "validation_status": "pending_human", "human_feedback": None}

    print(f"[epics] {len(epics)} epics générés")

    # ── 2. Persistance dans pm.epics ─────────────────────────
    if project_id:
        await save_epics(project_id, epics)
        print(f"[epics] {len(epics)} epics persistés en base")

    # ── 3. Retour dans le state ───────────────────────────────
    # node_validate lira state["epics"] pour construire ai_output
    return {
        "epics":             epics,
        "current_phase":     "epics",
        "validation_status": "pending_human",
        "human_feedback":    None,   # reset après utilisation
        "error":             None,
    }
