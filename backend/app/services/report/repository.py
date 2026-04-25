# app/services/report/repository.py
# ═══════════════════════════════════════════════════════════════
# Accès DB pour le rapport backlog PDF.
# Responsabilité unique : récupérer les données brutes depuis PostgreSQL.
# Aucune logique métier, aucune mise en forme.
# ═══════════════════════════════════════════════════════════════

import json
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.connection import AsyncSessionLocal
from app.database.models.crm.project   import Project
from app.database.models.crm.client    import Client
from app.database.models.hris.employee import Employee
from app.database.models.public.user   import User
from app.database.models.pm.epic       import Epic
from app.database.models.pm.user_story import UserStory
from app.database.models.pm.pipeline_state import PipelineState
from app.database.models.pm.enums      import PipelinePhaseEnum


async def get_project_full(project_id: int) -> dict | None:
    """
    Charge le projet avec son client et son project manager.
    Retourne None si le projet n'existe pas.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.client))
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return None

        # Charge le PM (employee → user) séparément
        pm_name  = None
        pm_email = None
        if project.project_manager_id:
            emp_result = await session.execute(
                select(Employee)
                .options(selectinload(Employee.user))
                .where(Employee.id == project.project_manager_id)
            )
            employee = emp_result.scalar_one_or_none()
            if employee and employee.user:
                pm_name  = employee.user.name
                pm_email = employee.user.email

        return {
            "id":          project.id,
            "name":        project.name,
            "status":      project.status,
            "start_date":  project.start_date,
            "end_date":    project.end_date,
            "jira_key":    project.jira_project_key,
            "created_at":  project.created_at,
            "client": {
                "name":          project.client.name          if project.client else "—",
                "industry":      project.client.industry      if project.client else None,
                "contact_email": project.client.contact_email if project.client else None,
            },
            "pm": {
                "name":  pm_name  or "—",
                "email": pm_email or "—",
            },
        }


async def get_epics_with_stories(project_id: int) -> list[dict]:
    """
    Charge tous les epics du projet avec leurs user stories.
    Inclut les données de couverture depuis pipeline_state (ai_output stories).
    Retourne une liste structurée prête à être utilisée par service.py.
    """
    async with AsyncSessionLocal() as session:

        # ── 1. Epics triés par id ─────────────────────────────
        epics_result = await session.execute(
            select(Epic)
            .where(Epic.project_id == project_id)
            .order_by(Epic.id)
        )
        db_epics = epics_result.scalars().all()

        if not db_epics:
            return []

        epic_ids = [e.id for e in db_epics]

        # ── 2. Stories triées par epic_id puis id ─────────────
        stories_result = await session.execute(
            select(UserStory)
            .where(UserStory.epic_id.in_(epic_ids))
            .order_by(UserStory.epic_id, UserStory.id)
        )
        db_stories = stories_result.scalars().all()

        # ── 3. Récupère les données de couverture (ai_output) ─
        # La phase stories stocke _review par story dans ai_output.stories
        coverage_map: dict[int, dict] = {}   # epic_id → review data
        ps_result = await session.execute(
            select(PipelineState)
            .where(
                PipelineState.project_id == project_id,
                PipelineState.phase      == PipelinePhaseEnum.PHASE_3_STORIES,
            )
        )
        pipeline_state = ps_result.scalar_one_or_none()
        if pipeline_state and pipeline_state.ai_output:
            ai_stories = pipeline_state.ai_output.get("stories", [])
            # Groupe les reviews par epic_id (index)
            for s in ai_stories:
                review   = s.get("_review")
                epic_idx = s.get("epic_id")
                if review and epic_idx is not None and epic_idx not in coverage_map:
                    coverage_map[epic_idx] = review

        # ── 4. Groupe les stories par epic ────────────────────
        stories_by_epic: dict[int, list] = {e.id: [] for e in db_epics}
        for s in db_stories:
            ac = []
            if s.acceptance_criteria:
                try:
                    ac = json.loads(s.acceptance_criteria)
                except Exception:
                    ac = [s.acceptance_criteria]
            stories_by_epic[s.epic_id].append({
                "id":                   s.id,
                "title":                s.title,
                "description":          s.description or "",
                "story_points":         s.story_points,
                "priority":             s.priority,
                "status":               s.status.value if s.status else "draft",
                "splitting_strategy":   s.splitting_strategy or "by_feature",
                "acceptance_criteria":  ac,
            })

        # ── 5. Assemble la liste finale ───────────────────────
        result = []
        for idx, epic in enumerate(db_epics):
            review = coverage_map.get(idx, {})
            result.append({
                "id":                epic.id,
                "title":             epic.title,
                "description":       epic.description or "",
                "splitting_strategy": epic.splitting_strategy or "by_feature",
                "stories":           stories_by_epic.get(epic.id, []),
                "coverage": {
                    "ok":                 review.get("coverage_ok", True),
                    "gaps":               review.get("gaps", []),
                    "scope_creep_issues": review.get("scope_creep_issues", []),
                    "quality_issues":     review.get("quality_issues", []),
                    "suggestions":        review.get("suggestions", []),
                },
            })

        return result
