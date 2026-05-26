# agents/pm/agents/staffing/steps/story_distribution/repository.py
# ═══════════════════════════════════════════════════════════════
# Persistance des sprints calculés au Step 3 (Story Distribution)
# dans la table project_management.sprints.
#
# Stratégie : delete-then-insert par project_id (idempotent comme
# persist_assignments). La source de vérité reste le state JSON ;
# la table sert au dashboard PM et au flow progress.
#
# Appelé depuis node_staffing.agent.py après que match_assignments
# retourne avec succès (pas au step 3, pour s'assurer que le matching
# a abouti avant de matérialiser les sprints).
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
from datetime import date
from sqlalchemy import delete, select

from app.database.connection import AsyncSessionLocal
from app.database.models.pm.sprint import Sprint


async def persist_sprints(project_id: int, distrib_result: dict) -> list[dict]:
    """
    distrib_result : dict (StoryDistributionResult.model_dump()).

    Insère une ligne par sprint dans project_management.sprints.
    Retourne la liste des sprints persistés enrichie de leur db_id, pour
    permettre au caller (node_staffing) de propager ces ids dans state
    (utile pour la sync Jira ensuite).
    """
    sprints_payload = distrib_result.get("sprints", []) or []
    rows: list[dict] = []

    for s in sprints_payload:
        if not isinstance(s, dict):
            continue
        sprint_number = s.get("sprint_number")
        if sprint_number is None:
            continue
        try:
            start = date.fromisoformat(s["start_date"])
            end   = date.fromisoformat(s["end_date"])
        except (KeyError, ValueError, TypeError):
            continue

        rows.append({
            "project_id":         project_id,
            "sprint_number":      sprint_number,
            "name":               f"Sprint {sprint_number}",
            "start_date":         start,
            "end_date":           end,
            "target_capacity_sp": int(s.get("target_capacity_sp", 0)),
            "actual_sp":          int(s.get("actual_sp", 0)),
            "status":             "planned",
        })

    enriched: list[dict] = []
    async with AsyncSessionLocal() as db:
        # ── Sauvegarder les liens Jira existants AVANT le delete ───
        # Sinon delete-then-insert ferait perdre les jira_sprint_id déjà
        # créés, et la prochaine sync recréerait des sprints Jira en double.
        existing_rows = (await db.execute(
            select(
                Sprint.sprint_number,
                Sprint.jira_sprint_id,
                Sprint.status,
                Sprint.actual_start_date,
                Sprint.actual_end_date,
            ).where(Sprint.project_id == project_id)
        )).all()
        preserved_by_sn = {
            r.sprint_number: {
                "jira_sprint_id":    r.jira_sprint_id,
                "status":            r.status,
                "actual_start_date": r.actual_start_date,
                "actual_end_date":   r.actual_end_date,
            }
            for r in existing_rows
        }

        # delete-then-insert : idempotent par project_id
        await db.execute(delete(Sprint).where(Sprint.project_id == project_id))
        await db.flush()
        if rows:
            # Réinjecte les champs préservés (jira_sprint_id + cycle de vie déjà avancé)
            for r in rows:
                prev = preserved_by_sn.get(r["sprint_number"])
                if prev:
                    if prev["jira_sprint_id"] is not None:
                        r["jira_sprint_id"] = prev["jira_sprint_id"]
                    # Si le sprint était déjà actif/completed, on ne reset pas à planned.
                    if prev["status"] and prev["status"] != "planned":
                        r["status"] = prev["status"]
                    if prev["actual_start_date"]:
                        r["actual_start_date"] = prev["actual_start_date"]
                    if prev["actual_end_date"]:
                        r["actual_end_date"] = prev["actual_end_date"]

            instances = [Sprint(**r) for r in rows]
            db.add_all(instances)
            await db.flush()
            # Récupérer les db_id générés
            for inst in instances:
                enriched.append({
                    "db_id":              inst.id,
                    "sprint_number":      inst.sprint_number,
                    "name":               inst.name,
                    "start_date":         inst.start_date.isoformat(),
                    "end_date":           inst.end_date.isoformat(),
                    "target_capacity_sp": inst.target_capacity_sp,
                    "actual_sp":          inst.actual_sp,
                    "status":             inst.status,
                    "jira_sprint_id":     inst.jira_sprint_id,
                })
        await db.commit()

    return enriched


async def clear_sprints(project_id: int) -> int:
    """Supprime tous les sprints d'un projet (utilisé lors d'un restart)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(Sprint).where(Sprint.project_id == project_id)
        )
        await db.commit()
    return result.rowcount or 0


async def get_sprints_by_project(project_id: int) -> list[dict]:
    """Retourne tous les sprints persistés d'un projet (pour dashboard / lecture API)."""
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Sprint)
            .where(Sprint.project_id == project_id)
            .order_by(Sprint.sprint_number)
        )).scalars().all()

    return [
        {
            "id":                 r.id,
            "sprint_number":      r.sprint_number,
            "name":               r.name,
            "start_date":         r.start_date.isoformat() if r.start_date else None,
            "end_date":           r.end_date.isoformat()   if r.end_date   else None,
            "target_capacity_sp": r.target_capacity_sp,
            "actual_sp":          r.actual_sp,
            "status":             r.status,
            "jira_sprint_id":     r.jira_sprint_id,
        }
        for r in rows
    ]


async def update_sprint_jira_id(sprint_db_id: int, jira_sprint_id: int) -> None:
    """Met à jour le jira_sprint_id d'un sprint persisté (post-sync Jira)."""
    async with AsyncSessionLocal() as db:
        sprint = await db.get(Sprint, sprint_db_id)
        if sprint:
            sprint.jira_sprint_id = jira_sprint_id
            await db.commit()


async def get_sprint_by_number(project_id: int, sprint_number: int) -> Sprint | None:
    """Récupère un sprint par (project_id, sprint_number). None si introuvable."""
    async with AsyncSessionLocal() as db:
        return (await db.execute(
            select(Sprint).where(
                Sprint.project_id    == project_id,
                Sprint.sprint_number == sprint_number,
            )
        )).scalar_one_or_none()


async def mark_sprint_active(sprint_db_id: int, actual_start: date) -> None:
    """Passe un sprint en 'active' avec sa date réelle de démarrage."""
    async with AsyncSessionLocal() as db:
        sprint = await db.get(Sprint, sprint_db_id)
        if sprint:
            sprint.status            = "active"
            sprint.actual_start_date = actual_start
            await db.commit()


async def mark_sprint_completed(sprint_db_id: int, actual_end: date) -> None:
    """Passe un sprint en 'completed' avec sa date réelle de clôture."""
    async with AsyncSessionLocal() as db:
        sprint = await db.get(Sprint, sprint_db_id)
        if sprint:
            sprint.status          = "completed"
            sprint.actual_end_date = actual_end
            await db.commit()
