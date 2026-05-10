# agents/pm/agents/staffing/steps/matching/repository.py
# ═══════════════════════════════════════════════════════════════
# Persistance des assignments Step 5 dans staffing_assignments.
#
# Stratégie : à chaque calcul du matching pour un projet, on REMPLACE
# l'ensemble des lignes (delete by project_id + insert). Idempotent et
# simple — la "source de vérité" reste le state JSON, la DB sert pour
# les requêtes dashboard cross-projets.
#
# Appelé depuis node_staffing.agent.py juste après que match_assignments
# retourne avec succès.
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
from sqlalchemy import delete

from app.database.connection import AsyncSessionLocal
from app.database.models.pm.staffing_assignment import StaffingAssignment


async def persist_assignments(project_id: int, matching_result: dict) -> int:
    """
    matching_result : dict (MatchingResult.model_dump()).

    Insère une ligne par profil de chaque story dans staffing_assignments.
    Retourne le nombre de lignes insérées.
    """
    matching_by_sprint = matching_result.get("matching_by_sprint", {}) or {}
    rows: list[dict] = []

    for key, sprint in matching_by_sprint.items():
        if not isinstance(sprint, dict):
            continue
        sprint_number = sprint.get("sprint_number") or _parse_sprint_key(key)
        for story in sprint.get("story_assignments", []):
            if not isinstance(story, dict):
                continue
            sid          = story.get("story_id")
            if sid is None:
                continue
            story_title  = story.get("story_title", "")
            story_points = story.get("story_points", 0)
            req_level    = story.get("required_level", "MID")
            req_skills   = story.get("required_skills", [])

            for a in story.get("assignments", []):
                if not isinstance(a, dict):
                    continue
                rows.append({
                    "project_id":         project_id,
                    "sprint_number":      sprint_number,
                    "story_id":           sid,
                    "story_title":        story_title,
                    "story_points":       story_points,
                    "required_profile":   a.get("required_profile", ""),
                    "required_level":     req_level,
                    "required_skills":    req_skills,
                    "employee_id":        a.get("employee_id"),
                    "employee_name":      a.get("employee_name"),
                    "employee_seniority": a.get("employee_seniority"),
                    "job_title":          a.get("job_title"),
                    "allocated_sp":       a.get("allocated_sp", 0.0),
                    "skill_score":        a.get("skill_score"),
                    "match_level":        a.get("match_level"),
                    "matched_skills":     a.get("matched_skills",   []),
                    "inferred_matches":   a.get("inferred_matches", []),
                    "missing_skills":     a.get("missing_skills",   []),
                    "status":             a.get("status", ""),
                    "warning_type":       a.get("warning_type"),
                    "seniority_downgrade_from": a.get("seniority_downgrade_from"),
                    "reason":             a.get("reason", ""),
                    "candidate_options":  a.get("candidate_options", []),
                })

    async with AsyncSessionLocal() as db:
        # delete-then-insert : idempotent par project_id
        await db.execute(
            delete(StaffingAssignment).where(StaffingAssignment.project_id == project_id)
        )
        # Flush explicite pour vider l'identity map avant les nouveaux INSERT,
        # évite les conflits si une ligne avait la même PK supposée.
        await db.flush()
        if rows:
            db.add_all([StaffingAssignment(**r) for r in rows])
            await db.flush()
        await db.commit()

    return len(rows)


async def clear_assignments(project_id: int) -> int:
    """Supprime toutes les lignes du projet (utilisé lors d'un restart)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(StaffingAssignment).where(StaffingAssignment.project_id == project_id)
        )
        await db.commit()
    return result.rowcount or 0


def _parse_sprint_key(key: str) -> int:
    try:
        return int(str(key).rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        return 0


# ──────────────────────────────────────────────────────────────
# Lecture pour endpoint API (dashboard PM)
# ──────────────────────────────────────────────────────────────

async def get_assignments_by_project(project_id: int) -> list[dict]:
    """Retourne toutes les affectations persistées d'un projet (pour le dashboard)."""
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(StaffingAssignment)
            .where(StaffingAssignment.project_id == project_id)
            .order_by(StaffingAssignment.sprint_number, StaffingAssignment.story_id)
        )).scalars().all()

    return [
        {
            "id":                 r.id,
            "sprint_number":      r.sprint_number,
            "story_id":           r.story_id,
            "story_title":        r.story_title,
            "story_points":       r.story_points,
            "required_profile":   r.required_profile,
            "required_level":     r.required_level,
            "required_skills":    r.required_skills or [],
            "employee_id":        r.employee_id,
            "employee_name":      r.employee_name,
            "employee_seniority": r.employee_seniority,
            "job_title":          r.job_title,
            "allocated_sp":       r.allocated_sp,
            "skill_score":        r.skill_score,
            "match_level":        r.match_level,
            "matched_skills":     r.matched_skills   or [],
            "inferred_matches":   r.inferred_matches or [],
            "missing_skills":     r.missing_skills   or [],
            "status":             r.status,
            "warning_type":       r.warning_type,
            "seniority_downgrade_from": r.seniority_downgrade_from,
            "reason":             r.reason,
            "candidate_options":  r.candidate_options or [],
        }
        for r in rows
    ]
