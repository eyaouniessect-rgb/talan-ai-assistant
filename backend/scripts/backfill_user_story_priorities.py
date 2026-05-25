# scripts/backfill_user_story_priorities.py
# ═══════════════════════════════════════════════════════════════
# Backfill priority_score / rank / is_critical sur user_stories
# pour les projets dont la phase Prioritization a déjà tourné AVANT
# l'ajout des colonnes (migration b3c4d5e6f7a8).
#
# Source des données :
#   - pipeline_state.ai_output (phase=phase_5_prioritization)
#     → liste priorities = [{story_id, priority_score, final_rank, is_critical?}]
#   - pipeline_state.ai_output (phase=phase_6_critical_path)
#     → critical_path = [story_id, ...]  (fallback pour is_critical si pas dans priorities)
#
# Usage :
#   cd backend && python -m scripts.backfill_user_story_priorities
# ═══════════════════════════════════════════════════════════════

import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update

from app.database.connection import AsyncSessionLocal
from app.database.models.pm.pipeline_state import PipelineState
from app.database.models.pm.user_story     import UserStory
from app.database.models.pm.enums          import PipelinePhaseEnum


async def backfill():
    updated_total = 0
    projects_touched = 0
    skipped_no_data = 0

    async with AsyncSessionLocal() as session:
        # 1. Récupérer toutes les phases prioritization
        prio_phases = (await session.execute(
            select(PipelineState).where(
                PipelineState.phase == PipelinePhaseEnum.PHASE_5_PRIORITIZATION
            )
        )).scalars().all()

        # 2. Récupérer toutes les phases CPM (pour fallback is_critical)
        cpm_phases = (await session.execute(
            select(PipelineState).where(
                PipelineState.phase == PipelinePhaseEnum.PHASE_6_CRITICAL_PATH
            )
        )).scalars().all()
        critical_by_project: dict[int, set[int]] = {}
        for cp in cpm_phases:
            cpath = (cp.ai_output or {}).get("critical_path") or []
            critical_by_project[cp.project_id] = {int(sid) for sid in cpath if sid is not None}

        # 3. Pour chaque phase prio : itérer ses priorities[] et UPDATE user_stories
        for ps in prio_phases:
            project_id = ps.project_id
            priorities = (ps.ai_output or {}).get("priorities") or []
            if not priorities:
                skipped_no_data += 1
                continue

            critical_set = critical_by_project.get(project_id, set())
            project_updates = 0

            for p in priorities:
                sid = p.get("story_id")
                if sid is None:
                    continue
                # is_critical : préférer la valeur dans priorities, fallback sur CPM
                if "is_critical" in p and p["is_critical"] is not None:
                    is_critical = bool(p["is_critical"])
                else:
                    is_critical = int(sid) in critical_set

                result = await session.execute(
                    update(UserStory)
                    .where(UserStory.id == sid)
                    .values(
                        priority_score = float(p.get("priority_score") or 0.0),
                        rank           = int(p.get("final_rank") or 0),
                        is_critical    = is_critical,
                    )
                )
                if result.rowcount and result.rowcount > 0:
                    project_updates += result.rowcount

            if project_updates > 0:
                projects_touched += 1
                updated_total += project_updates
                print(f"  projet {project_id} : {project_updates} stories mises à jour")

        await session.commit()

    print()
    print(f"OK - Backfill termine : {updated_total} stories sur {projects_touched} projets.")
    if skipped_no_data:
        print(f"  ({skipped_no_data} phases skippees car priorities[] vide)")


if __name__ == "__main__":
    asyncio.run(backfill())
