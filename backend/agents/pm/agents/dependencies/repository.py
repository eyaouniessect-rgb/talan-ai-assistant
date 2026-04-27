# agents/pm/agents/dependencies/repository.py
# Repository — persistance des dépendances entre User Stories

from sqlalchemy import select, delete

from app.database.connection import AsyncSessionLocal
from app.database.models.pm.story_dependency import StoryDependency


async def save_story_dependencies(project_id: int, deps: list[dict]) -> None:
    """
    Supprime les dépendances existantes du projet puis insère les nouvelles.
    Chaque dep doit contenir : from_story_id, to_story_id, dependency_type,
    relation_type, is_blocking, level, reason.
    """
    async with AsyncSessionLocal() as session:
        # Supprimer via les user_stories du projet
        await session.execute(
            delete(StoryDependency).where(
                StoryDependency.story_id.in_(
                    select(
                        __import__(
                            "app.database.models.pm.user_story",
                            fromlist=["UserStory"]
                        ).UserStory.id
                    ).where(
                        __import__(
                            "app.database.models.pm.user_story",
                            fromlist=["UserStory"]
                        ).UserStory.epic_id.in_(
                            select(
                                __import__(
                                    "app.database.models.pm.epic",
                                    fromlist=["Epic"]
                                ).Epic.id
                            ).where(
                                __import__(
                                    "app.database.models.pm.epic",
                                    fromlist=["Epic"]
                                ).Epic.project_id == project_id
                            )
                        )
                    )
                )
            )
        )

        orm_deps = [
            StoryDependency(
                story_id            = d["from_story_id"],
                depends_on_story_id = d["to_story_id"],
                dependency_type     = d.get("dependency_type", "functional"),
                relation_type       = d.get("relation_type", "FS"),
                is_blocking         = d.get("is_blocking", True),
                level               = d.get("level", "intra_epic"),
                reason              = d.get("reason", ""),
            )
            for d in deps
        ]
        session.add_all(orm_deps)
        await session.commit()

    print(f"[deps/repo] {len(orm_deps)} dépendances persistées pour projet {project_id}")


async def get_story_dependencies(project_id: int) -> list[dict]:
    """Retourne toutes les dépendances d'un projet sous forme de dicts."""
    from app.database.models.pm.user_story import UserStory
    from app.database.models.pm.epic import Epic

    async with AsyncSessionLocal() as session:
        story_ids_q = (
            select(UserStory.id)
            .join(Epic, UserStory.epic_id == Epic.id)
            .where(Epic.project_id == project_id)
        )
        result = await session.execute(
            select(StoryDependency).where(
                StoryDependency.story_id.in_(story_ids_q)
            )
        )
        rows = result.scalars().all()

    return [
        {
            "from_story_id":   r.story_id,
            "to_story_id":     r.depends_on_story_id,
            "dependency_type": r.dependency_type,
            "relation_type":   r.relation_type,
            "is_blocking":     r.is_blocking,
            "level":           r.level,
            "reason":          r.reason,
        }
        for r in rows
    ]


async def delete_story_dependencies(project_id: int) -> None:
    """Supprime toutes les dépendances d'un projet."""
    from app.database.models.pm.user_story import UserStory
    from app.database.models.pm.epic import Epic

    async with AsyncSessionLocal() as session:
        story_ids_q = (
            select(UserStory.id)
            .join(Epic, UserStory.epic_id == Epic.id)
            .where(Epic.project_id == project_id)
        )
        await session.execute(
            delete(StoryDependency).where(
                StoryDependency.story_id.in_(story_ids_q)
            )
        )
        await session.commit()
