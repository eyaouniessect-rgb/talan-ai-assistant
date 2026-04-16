# agents/pm/agents/stories/repository.py
# ═══════════════════════════════════════════════════════════════
# Repository des User Stories — persistance DB
#
# Mapping epic_id :
#   Le LLM génère epic_id = index dans le tableau des epics (0, 1, 2…).
#   save_stories() récupère les epics du projet depuis la DB (triés par id)
#   et mappe index → epic.id réel avant insertion.
#
# Idempotent : supprime les stories existantes avant de réinsérer.
# ═══════════════════════════════════════════════════════════════

import json

from sqlalchemy import select, delete

from app.database.connection import AsyncSessionLocal
from app.database.models.pm.epic       import Epic
from app.database.models.pm.user_story import UserStory
from app.database.models.pm.enums      import StoryStatusEnum


async def save_stories(project_id: int, stories: list[dict]) -> list[UserStory]:
    """
    Supprime les user stories existantes du projet, puis insère les nouvelles.
    Utilisé à chaque génération (initiale ou après rejet PM).

    Mapping epic_id :
        Le LLM utilise l'index de l'epic dans le tableau (0, 1, 2…).
        On récupère les epics du projet triés par id pour retrouver l'id DB réel.

    Retourne la liste des UserStory ORM créées (avec leurs IDs générés).
    """
    async with AsyncSessionLocal() as session:

        # ── 1. Récupérer les epics du projet (ordre d'insertion) ─
        result    = await session.execute(
            select(Epic)
            .where(Epic.project_id == project_id)
            .order_by(Epic.id)
        )
        db_epics = result.scalars().all()

        # Mapping index LLM → ID DB réel
        # ex: epic_id=0 → db_epics[0].id, epic_id=1 → db_epics[1].id
        index_to_db_id = {i: e.id for i, e in enumerate(db_epics)}

        if not db_epics:
            print(f"[stories/repo] ❌ ERREUR CRITIQUE — aucun epic en DB pour projet {project_id} → 0 stories sauvegardées")
            return []

        # ── 2. Supprimer les stories existantes du projet ─────────
        # user_stories liées aux epics du projet
        epic_ids = [e.id for e in db_epics]
        if epic_ids:
            await session.execute(
                delete(UserStory).where(UserStory.epic_id.in_(epic_ids))
            )

        # ── 3. Insérer les nouvelles stories ──────────────────────
        orm_stories  = []
        saved_dicts  = []   # story dicts correspondant à orm_stories (pour écrire db_id)
        for i, s in enumerate(stories):
            epic_idx  = s.get("epic_id", 0)
            db_epic_id = index_to_db_id.get(epic_idx)

            if db_epic_id is None:
                print(f"[stories/repo] ⚠ Story {i} : epic_id={epic_idx} introuvable dans le projet, ignorée")
                continue

            # acceptance_criteria stocké en JSON text
            ac = s.get("acceptance_criteria", [])
            ac_text = json.dumps(ac, ensure_ascii=False) if ac else None

            orm_s = UserStory(
                epic_id             = db_epic_id,
                title               = s["title"],
                description         = s.get("description", ""),
                story_points        = s.get("story_points"),
                splitting_strategy  = s.get("splitting_strategy", "by_feature"),
                acceptance_criteria = ac_text,
                status              = StoryStatusEnum.DRAFT,
                ai_metadata         = {"source": "llm_generated", "llm_epic_idx": epic_idx},
            )
            orm_stories.append(orm_s)
            saved_dicts.append(s)

        session.add_all(orm_stories)
        await session.commit()

        for st in orm_stories:
            await session.refresh(st)

        # ── 4. Écrire db_id en retour dans les dicts (pour l'ai_output) ──
        for story_dict, orm_s in zip(saved_dicts, orm_stories):
            story_dict["db_id"] = orm_s.id

        print(f"[stories/repo] ✓ {len(orm_stories)} stories persistées (projet {project_id})")
        return orm_stories


async def get_stories(project_id: int) -> list[UserStory]:
    """Retourne toutes les stories du projet, triées par epic_id puis id."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserStory)
            .join(Epic, UserStory.epic_id == Epic.id)
            .where(Epic.project_id == project_id)
            .order_by(UserStory.epic_id, UserStory.id)
        )
        return result.scalars().all()


async def update_story(story_id: int, updates: dict) -> bool:
    """Met à jour les champs éditables d'une story. Retourne True si trouvée."""
    from sqlalchemy import update as sa_update
    async with AsyncSessionLocal() as session:
        values: dict = {}
        if "title" in updates and updates["title"]:
            values["title"] = updates["title"]
        if "description" in updates:
            values["description"] = updates["description"]
        if "story_points" in updates and updates["story_points"] is not None:
            values["story_points"] = int(updates["story_points"])
        if "acceptance_criteria" in updates:
            ac = updates["acceptance_criteria"]
            values["acceptance_criteria"] = json.dumps(ac, ensure_ascii=False) if isinstance(ac, list) else ac

        if not values:
            return False

        result = await session.execute(
            sa_update(UserStory).where(UserStory.id == story_id).values(**values)
        )
        await session.commit()
        return result.rowcount > 0


async def delete_story(story_id: int) -> bool:
    """Supprime une story. Retourne True si trouvée et supprimée."""
    from sqlalchemy import delete as sa_delete
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa_delete(UserStory).where(UserStory.id == story_id)
        )
        await session.commit()
        return result.rowcount > 0


async def update_story_jira_key(story_db_id: int, jira_key: str) -> None:
    """Met à jour jira_issue_key d'une story après synchronisation Jira."""
    from sqlalchemy import update as sa_update
    async with AsyncSessionLocal() as session:
        await session.execute(
            sa_update(UserStory)
            .where(UserStory.id == story_db_id)
            .values(jira_issue_key=jira_key)
        )
        await session.commit()
