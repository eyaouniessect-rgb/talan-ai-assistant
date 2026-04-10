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
                status             = EpicStatusEnum.DRAFT,
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
