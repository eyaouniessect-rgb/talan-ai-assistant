# agents/pm/agents/monitoring/agent.py
# Phase 9 — Plan de monitoring continu
# STUB — implémentation complète à venir.
# Note : pas de validation humaine — cette phase s'exécute toujours jusqu'à END.

from sqlalchemy import select

from agents.pm.state import PMPipelineState
from agents.pm.db import upsert_pipeline_state
from app.database.connection import AsyncSessionLocal
from app.database.models.crm.project import Project
from app.database.models.pm.enums import (
    PipelinePhaseEnum, PipelineStatusEnum, ProjectGlobalStatus,
)
from app.database.models.pm.pipeline_state import PipelineState


async def node_monitoring(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 9 : plan de monitoring.

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

    print(f"[monitoring] Phase 9 | projet={project_id} (stub)")

    monitoring_plan = {
        "kpis":             [],
        "alerts":           [],
        "review_frequency": "weekly",
        "jira_webhooks":    [],
    }

    # Phase 9 = VALIDATED directement (pas de validation humaine)
    if project_id:
        await upsert_pipeline_state(
            project_id = project_id,
            phase      = PipelinePhaseEnum.PHASE_9_MONITORING,
            status     = PipelineStatusEnum.VALIDATED,
            ai_output  = monitoring_plan,
        )
        print(f"[monitoring] pipeline_state phase 9 persisté (VALIDATED)")

        # ── Passe le projet à PIPELINE_DONE si toutes les phases sont VALIDATED ──
        # Le endpoint /validate ne peut pas le faire pour la phase monitoring,
        # parce que monitoring tourne en arrière-plan APRÈS que validate ait
        # déjà renvoyé sa réponse (avec count=7/8). C'est donc ici qu'on
        # finalise le statut global du projet.
        try:
            async with AsyncSessionLocal() as session:
                all_states = (await session.execute(
                    select(PipelineState).where(PipelineState.project_id == project_id)
                )).scalars().all()
                validated_count = sum(
                    1 for p in all_states if p.status == PipelineStatusEnum.VALIDATED
                )
                if validated_count >= 8:
                    proj = (await session.execute(
                        select(Project).where(Project.id == project_id)
                    )).scalar_one_or_none()
                    if proj and proj.status != ProjectGlobalStatus.PIPELINE_DONE.value:
                        proj.status = ProjectGlobalStatus.PIPELINE_DONE.value
                        await session.commit()
                        print(f"[monitoring] projet {project_id} → status=pipeline_done")
        except Exception as e:
            print(f"[monitoring] ⚠️  maj crm.projects.status échouée : {e}")

    return {
        "monitoring_plan":   monitoring_plan,
        "current_phase":     "monitoring",
        "validation_status": "validated",
        "error":             None,
    }
