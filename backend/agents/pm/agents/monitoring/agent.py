# agents/pm/agents/monitoring/agent.py
# Phase 12 — Plan de monitoring continu
# STUB — implémentation complète à venir.
# Note : pas de validation humaine — cette phase s'exécute toujours jusqu'à END.

from agents.pm.state import PMPipelineState
from agents.pm.db import upsert_pipeline_state
from app.database.models.pm.enums import PipelinePhaseEnum, PipelineStatusEnum


async def node_monitoring(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 12 : plan de monitoring.

    Le LLM génère :
      - KPIs à surveiller (nom, cible, unité, fréquence)
      - Alertes (condition, sévérité, canal de notification)
      - Fréquence de revue (daily/weekly/bi-weekly)
      - Événements Jira à surveiller via webhooks

    Pas de validation humaine → persiste directement en VALIDATED.
    """
    project_id = state.get("project_id")
    sprints    = state.get("sprints", [])
    staffing   = state.get("staffing", {})

    print(f"[monitoring] Phase 12 | projet={project_id} (stub)")

    monitoring_plan = {
        "kpis":             [],
        "alerts":           [],
        "review_frequency": "weekly",
        "jira_webhooks":    [],
    }

    # Phase 12 = VALIDATED directement (pas de validation humaine)
    if project_id:
        await upsert_pipeline_state(
            project_id = project_id,
            phase      = PipelinePhaseEnum.PHASE_12_MONITORING,
            status     = PipelineStatusEnum.VALIDATED,
            ai_output  = monitoring_plan,
        )
        print(f"[monitoring] pipeline_state phase 12 persisté (VALIDATED)")

    return {
        "monitoring_plan":   monitoring_plan,
        "current_phase":     "monitoring",
        "validation_status": "validated",
        "error":             None,
    }
