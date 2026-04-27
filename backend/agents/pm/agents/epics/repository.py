# agents/pm/agents/epics/repository.py
# ═══════════════════════════════════════════════════════════════
# Repository des Epics — persistance DB
#
# Responsabilités :
#   - Insérer les epics en bulk dans pm.epics
#   - Supprimer les epics existants avant une réinsertion (rejet PM)
#   - La persistance pipeline_state est gérée par node_validate
#     (ce repository ne touche PAS à pm.pipeline_state)
# ═══════════════════════════════════════════════════════════════

from sqlalchemy import delete

from app.database.connection import AsyncSessionLocal
from app.database.models.pm.epic import Epic
from app.database.models.pm.enums import EpicStatusEnum


async def save_epics(project_id: int, epics: list[dict]) -> list[Epic]:
    """
    Supprime les epics existants pour ce projet, puis insère les nouveaux.
    Utilisé à chaque génération (initiale ou après rejet PM).

    Retourne la liste des Epic ORM créés (avec leurs IDs générés).
    """
    async with AsyncSessionLocal() as session:
        # ── Supprimer les anciens epics ───────────────────────
        await session.execute(
            delete(Epic).where(Epic.project_id == project_id)
        )

        # ── Insérer les nouveaux epics ────────────────────────
        orm_epics = [
            Epic(
                project_id         = project_id,
                title              = epic["title"],
                description        = epic["description"],
                splitting_strategy = epic["splitting_strategy"],
                status             = EpicStatusEnum.GENERATED,
                ai_metadata        = {"source": "llm_generated"},
            )
            for epic in epics
        ]
        session.add_all(orm_epics)
        await session.commit()

        # Refresh pour récupérer les IDs générés
        for e in orm_epics:
            await session.refresh(e)

        return orm_epics


async def update_epic(epic_id: int, updates: dict) -> bool:
    """Met à jour title, description et/ou splitting_strategy d'un epic."""
    from sqlalchemy import update as sa_update
    async with AsyncSessionLocal() as session:
        values: dict = {}
        if "title" in updates and updates["title"]:
            values["title"] = updates["title"]
        if "description" in updates:
            values["description"] = updates["description"]
        if "splitting_strategy" in updates and updates["splitting_strategy"]:
            values["splitting_strategy"] = updates["splitting_strategy"]
        if not values:
            return False
        result = await session.execute(
            sa_update(Epic).where(Epic.id == epic_id).values(**values)
        )
        await session.commit()
        return result.rowcount > 0


async def delete_epic(epic_id: int) -> bool:
    """Supprime un epic (et ses stories en cascade). Retourne True si trouvé."""
    from sqlalchemy import delete as sa_delete
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa_delete(Epic).where(Epic.id == epic_id)
        )
        await session.commit()
        return result.rowcount > 0


async def add_epic(project_id: int, epic_data: dict) -> Epic:
    """Insère un nouvel epic pour ce projet. Retourne l'ORM créé (avec id)."""
    async with AsyncSessionLocal() as session:
        orm_e = Epic(
            project_id         = project_id,
            title              = epic_data["title"],
            description        = epic_data.get("description", ""),
            splitting_strategy = epic_data.get("splitting_strategy", "by_feature"),
            status             = EpicStatusEnum.GENERATED,
            ai_metadata        = {"source": "manual"},
        )
        session.add(orm_e)
        await session.commit()
        await session.refresh(orm_e)
        return orm_e


async def update_epic_jira_key(epic_db_id: int, jira_key: str) -> None:
    """Met à jour jira_epic_key d'un epic après synchronisation Jira."""
    from sqlalchemy import update as sa_update
    async with AsyncSessionLocal() as session:
        await session.execute(
            sa_update(Epic)
            .where(Epic.id == epic_db_id)
            .values(jira_epic_key=jira_key)
        )
        await session.commit()


async def get_epics(project_id: int) -> list[Epic]:
    """Retourne tous les epics d'un projet, triés par id."""
    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Epic)
            .where(Epic.project_id == project_id)
            .order_by(Epic.id)
        )
        return result.scalars().all()
