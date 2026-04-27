# agents/pm/db/db.py
# ═══════════════════════════════════════════════════════════════
# Helpers de persistance DB partagés par tous les agents du pipeline PM.
#
# Fonctions :
#   - upsert_pipeline_state   : crée ou met à jour pm.pipeline_state
#   - get_pipeline_state      : lit l'état d'une phase pour un projet
#   - get_all_pipeline_states : toutes les phases d'un projet
#   - get_employee_id_by_user : résout user_id → employee_id (hris)
#   - phase_str_to_enum       : convertit string phase → PipelinePhaseEnum
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from datetime import datetime, timezone, UTC
from typing import Optional, Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.connection import AsyncSessionLocal
from app.database.models.pm.pipeline_state import PipelineState
from app.database.models.pm.enums import PipelinePhaseEnum, PipelineStatusEnum
from app.database.models.hris.employee import Employee
from app.database.models.public.user import User


# ──────────────────────────────────────────────────────────────
# UPSERT pipeline_state
# ──────────────────────────────────────────────────────────────

async def upsert_pipeline_state(
    project_id:   int,
    phase:        PipelinePhaseEnum,
    status:       PipelineStatusEnum,
    ai_output:    Optional[Any]      = None,
    pm_comment:   Optional[str]      = None,
    validated_by: Optional[int]      = None,
    validated_at: Optional[datetime] = None,
) -> PipelineState:
    """
    Insère ou met à jour la ligne pm.pipeline_state pour (project_id, phase).
    Idempotent grâce à ON CONFLICT (uq_pipeline_project_phase) DO UPDATE.
    """
    async with AsyncSessionLocal() as session:
        values = {
            "project_id": project_id,
            "phase":      phase,
            "status":     status,
        }
        if ai_output   is not None: values["ai_output"]    = ai_output
        if pm_comment  is not None: values["pm_comment"]   = pm_comment
        if validated_by is not None: values["validated_by"] = validated_by
        if validated_at is not None: values["validated_at"] = validated_at

        # Construire le set_ dynamiquement pour ne pas écraser ai_output avec None
        # lors des appels de validation (qui ne passent pas de nouvel ai_output)
        set_ = {"status": status, "updated_at": datetime.utcnow()}
        if ai_output    is not None: set_["ai_output"]    = ai_output
        if pm_comment   is not None: set_["pm_comment"]   = pm_comment
        if validated_by is not None: set_["validated_by"] = validated_by
        if validated_at is not None: set_["validated_at"] = validated_at

        stmt = (
            pg_insert(PipelineState)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_pipeline_project_phase",
                set_=set_,
            )
            .returning(PipelineState)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


# ──────────────────────────────────────────────────────────────
# GET pipeline_state
# ──────────────────────────────────────────────────────────────

async def get_pipeline_state(
    project_id: int,
    phase:      PipelinePhaseEnum,
) -> Optional[PipelineState]:
    """Retourne l'état d'une phase pour un projet, ou None si inexistant."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PipelineState).where(
                PipelineState.project_id == project_id,
                PipelineState.phase      == phase,
            )
        )
        return result.scalar_one_or_none()


async def get_all_pipeline_states(project_id: int) -> list[PipelineState]:
    """Retourne toutes les lignes pm.pipeline_state pour un projet, triées par id."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PipelineState)
            .where(PipelineState.project_id == project_id)
            .order_by(PipelineState.id)
        )
        return result.scalars().all()


# ──────────────────────────────────────────────────────────────
# RÉSOLUTION user_id → employee_id
# ──────────────────────────────────────────────────────────────

async def get_employee_id_by_user(user_id: int) -> Optional[int]:
    """Résout user_id (public.users) → employee_id (hris.employees) via user_id FK."""
    async with AsyncSessionLocal() as session:
        emp_result = await session.execute(
            select(Employee).where(Employee.user_id == user_id)
        )
        employee = emp_result.scalar_one_or_none()
        return employee.id if employee else None


# ──────────────────────────────────────────────────────────────
# MAPPING phase string → PipelinePhaseEnum
# ──────────────────────────────────────────────────────────────

_PHASE_STR_TO_ENUM: dict[str, PipelinePhaseEnum] = {
    "extract":        PipelinePhaseEnum.PHASE_1_EXTRACTION,
    "epics":          PipelinePhaseEnum.PHASE_2_EPICS,
    "stories":        PipelinePhaseEnum.PHASE_3_STORIES,

    "story_deps":     PipelinePhaseEnum.PHASE_5_STORY_DEPS,
    "prioritization": PipelinePhaseEnum.PHASE_6_PRIORITIZATION,
    "tasks":          PipelinePhaseEnum.PHASE_7_TASKS,
    "task_deps":      PipelinePhaseEnum.PHASE_8_TASK_DEPS,
    "cpm":            PipelinePhaseEnum.PHASE_9_CRITICAL_PATH,
    "sprints":        PipelinePhaseEnum.PHASE_10_SPRINT_PLANNING,
    "staffing":       PipelinePhaseEnum.PHASE_11_STAFFING,
    "monitoring":     PipelinePhaseEnum.PHASE_12_MONITORING,
}


def phase_str_to_enum(phase: str) -> PipelinePhaseEnum:
    """Convertit une string de phase (ex: "epics") en PipelinePhaseEnum."""
    result = _PHASE_STR_TO_ENUM.get(phase)
    if result is None:
        raise ValueError(f"Phase inconnue : '{phase}'")
    return result
