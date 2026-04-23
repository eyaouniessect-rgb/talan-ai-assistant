# agents/pm/graph/node_validate.py
# ═══════════════════════════════════════════════════════════════
# Noeud de validation humaine — partagé par toutes les phases 2→11
#
# Flux :
#   phase_N → node_validate → (validated) → jira_sync → phase_N+1
#                           → (rejected)  → phase_N   (relancée avec feedback)
#
# Responsabilités :
#   1. Extraire le résultat IA de la phase courante depuis le state
#   2. Persister en DB (status=PENDING_VALIDATION) AVANT de suspendre
#      → le frontend voit les données même si le process redémarre
#   3. Suspendre via interrupt() → attendre POST /pipeline/:id/validate
#   4. À la reprise, retourner validated ou rejected + feedback
# ═══════════════════════════════════════════════════════════════

from langgraph.types import interrupt

from agents.pm.state import PMPipelineState
from agents.pm.db import upsert_pipeline_state, phase_str_to_enum
from app.database.models.pm.enums import PipelineStatusEnum


async def node_validate(state: PMPipelineState) -> dict:
    """
    Suspend le graph et attend la validation humaine du PM.
    Persiste le résultat IA en base AVANT la suspension.
    """
    phase      = state.get("current_phase", "unknown")
    project_id = state.get("project_id")

    # ── 1. Extraire le résultat IA de la phase courante ───────
    ai_output = _get_phase_output(state, phase)

    # ── 2. Persister en base AVANT de suspendre ───────────────
    if project_id:
        try:
            phase_enum = phase_str_to_enum(phase)
            await upsert_pipeline_state(
                project_id = project_id,
                phase      = phase_enum,
                status     = PipelineStatusEnum.PENDING_VALIDATION,
                ai_output  = ai_output,
            )
        except Exception as e:
            # Ne PAS laisser une erreur DB crasher le graph entier.
            # Le interrupt() ci-dessous doit toujours s'exécuter.
            print(f"[node_validate] ⚠ Échec persistence phase '{phase}': {type(e).__name__}: {e}")

    # ── 3. Suspendre le graph ─────────────────────────────────
    decision = interrupt({
        "phase":     phase,
        "ai_output": ai_output,
        "message":   f"Phase '{phase}' terminée. Validez ou rejetez le résultat.",
    })

    # ── 4. Traitement de la décision ──────────────────────────
    approved = decision.get("approved", False)
    feedback = decision.get("feedback", None)

    if approved:
        return {
            "validation_status": "validated",
            "human_feedback":    None,
        }

    return {
        "validation_status": "rejected",
        "human_feedback":    feedback or "Le PM a rejeté sans préciser de raison.",
    }


# ──────────────────────────────────────────────────────────────
# EXTRACTION DU RÉSULTAT IA PAR PHASE
# ──────────────────────────────────────────────────────────────

def _get_phase_output(state: PMPipelineState, phase: str) -> dict:
    """
    Extrait le résultat de la phase courante depuis le state LangGraph.
    Retourne un dict sérialisable (stocké en JSONB dans pm.pipeline_state).
    """
    # Phase 1 — extraction : stats CDC + sécurité + résultat VLM
    if phase == "extract":
        cdc_text                 = state.get("cdc_text", "")
        # Priorité : page_count réel (PDF pymupdf) sinon estimation depuis nb chars
        page_count               = state.get("page_count") or max(1, len(cdc_text) // 2000)
        image_count              = state.get("image_count") or 0
        vlm_doc_info             = state.get("vlm_doc_info") or {}
        security_scan            = state.get("security_scan")
        architecture_detected    = state.get("architecture_detected", False)
        architecture_description = state.get("architecture_description")
        architecture_details     = state.get("architecture_details")
        return {
            "filename":                 None,
            "file_size":                None,
            "pages_est":                page_count,
            "chars":                    len(cdc_text),
            "image_count":              image_count,
            "oversized_pages":          vlm_doc_info.get("oversized_pages", []),
            "preview":                  cdc_text,
            "security_scan":            security_scan,
            "architecture_detected":    architecture_detected,
            "architecture_description": architecture_description,
            "architecture_details":     architecture_details,
        }

    # Phase 3 — stories : on inclut aussi les epics pour que le front affiche les titres
    if phase == "stories":
        return {
            "stories": state.get("stories", []),
            "epics":   state.get("epics",   []),
        }

    # Phase 4 — refinement : résultat Round 1 + données pour la revue story-par-story
    if phase == "refinement":
        return {
            "refined_stories":       state.get("refined_stories",      []),
            "stories_before_round":  state.get("stories_before_round", []),
            "refinement_rounds":     state.get("refinement_rounds",    []),
            "current_round":         state.get("current_round",        1),
            "consensus":             state.get("refinement_consensus", False),
            "epics":                 state.get("epics",                []),
            "awaiting_round_review": True,   # toujours True à la sortie du nœud
        }

    phase_field_map = {
        "epics":           "epics",
        "story_deps":      "story_dependencies",
        "prioritization":  "priorities",
        "tasks":           "tasks",
        "task_deps":       "task_dependencies",
        "cpm":             "cpm_result",
        "sprints":         "sprints",
        "staffing":        "staffing",
    }

    field = phase_field_map.get(phase)
    if field and state.get(field) is not None:
        return {field: state[field]}

    return {"phase": phase, "data": None}
