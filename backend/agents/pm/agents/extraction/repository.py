# agents/pm/agents/extraction/repository.py
# ═══════════════════════════════════════════════════════════════
# Repository d'extraction — persistance DB
#
# Persiste le résultat de la phase 1 (EXTRACTION) en base.
# Phase 1 est toujours validée automatiquement (pas de validation humaine).
# ═══════════════════════════════════════════════════════════════

from agents.pm.db import upsert_pipeline_state
from app.database.models.pm.enums import PipelinePhaseEnum, PipelineStatusEnum


async def save_extraction_result(
    project_id: int,
    filename:   str,
    cdc_text:   str,
) -> None:
    """
    Persiste la phase 1 (EXTRACTION) en base avec status=VALIDATED.
    ai_output contient le nom du fichier, le nombre de caractères et un aperçu.
    """
    await upsert_pipeline_state(
        project_id = project_id,
        phase      = PipelinePhaseEnum.PHASE_1_EXTRACTION,
        status     = PipelineStatusEnum.VALIDATED,
        ai_output  = {
            "filename":  filename,
            "chars":     len(cdc_text),
            "pages_est": max(1, len(cdc_text) // 2000),
            "preview":   cdc_text[:500],
        },
    )
