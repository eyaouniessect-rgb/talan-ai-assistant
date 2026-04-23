# agents/pm/agents/refinement/repository.py
# ═══════════════════════════════════════════════════════════════
# Persistance des stories raffinées — Phase 4
#
# Stratégie : UPDATE les user_stories existantes (pas de réinsertion)
#   - status → "refined"
#   - champs modifiés : title, description, story_points, acceptance_criteria
# Les stories sans db_id sont ignorées (cas edge).
# ═══════════════════════════════════════════════════════════════

import json

from sqlalchemy import update as sa_update

from app.database.connection import AsyncSessionLocal
from app.database.models.pm.user_story import UserStory
from app.database.models.pm.enums      import StoryStatusEnum


async def save_refined_stories(
    project_id: int,
    refined_stories: list[dict],
) -> None:
    """
    Met à jour les user_stories en DB avec les champs raffinés.
    Passe leur status à 'refined'.

    Utilise db_id (présent depuis save_stories Phase 3) pour identifier les lignes.
    """
    print(f"\n[refinement/repo] ══ SAUVEGARDE EN BASE projet={project_id} ══")
    print(f"[refinement/repo]   {len(refined_stories)} stories à traiter")

    async with AsyncSessionLocal() as session:
        updated = 0
        skipped = 0
        for pos, story in enumerate(refined_stories):
            db_id = story.get("db_id")
            if not db_id:
                print(f"[refinement/repo]   [{pos:02d}] ⚠ IGNORÉ — pas de db_id (title='{str(story.get('title',''))[:35]}')")
                skipped += 1
                continue

            ac = story.get("acceptance_criteria", [])
            ac_text = json.dumps(ac, ensure_ascii=False) if isinstance(ac, list) else ac

            values: dict = {
                "status": StoryStatusEnum.REFINED,
            }
            if story.get("title"):
                values["title"] = story["title"]
            if "description" in story:
                values["description"] = story.get("description", "")
            if story.get("story_points") is not None:
                values["story_points"] = int(story["story_points"])
            if ac:
                values["acceptance_criteria"] = ac_text

            champs = [k for k in values if k != "status"]
            print(f"[refinement/repo]   [{pos:02d}] UPDATE db_id={db_id} | epic={story.get('epic_id')} | sp={story.get('story_points')} | champs={champs} | title='{str(story.get('title',''))[:35]}'")

            await session.execute(
                sa_update(UserStory)
                .where(UserStory.id == db_id)
                .values(**values)
            )
            updated += 1

        await session.commit()
        print(f"[refinement/repo] ✓ {updated} mises à jour | {skipped} ignorées (sans db_id) | projet={project_id}")
        print(f"[refinement/repo] ══════════════════════════════════════════════\n")
