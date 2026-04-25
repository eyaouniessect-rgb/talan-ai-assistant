# agents/pm/agents/epics/agent.py
# Phase 2 — Génération et correction des Epics
#
# Cas 1 — Première génération (human_feedback=None, pas d'epics existants) :
#   → generate_epics() depuis le CDC
#
# Cas 2 — Rejet GLOBAL (human_feedback set, targeted_epic_ids vide) :
#   → improve_all_epics() : passe les epics existants + feedback au LLM
#   → LLM modifie/ajoute/renomme sans régénérer depuis zéro
#
# Cas 3 — Rejet CIBLÉ (targeted_epic_ids non vide) :
#   → improve_targeted_epics() pour les epics cochés seulement
#   → db_id existant → UPDATE  |  db_id null → INSERT (scission)
#   → Les autres epics restent intacts

from agents.pm.state import PMPipelineState
from agents.pm.agents.epics.service    import generate_epics, improve_all_epics, improve_targeted_epics
from agents.pm.agents.epics.repository import save_epics, get_epics, update_epic, add_epic, delete_epic


async def node_epics(state: PMPipelineState) -> dict:
    """Noeud LangGraph — Phase 2 : génération des Epics."""
    project_id        = state.get("project_id")
    cdc_text          = state.get("cdc_text", "")
    human_feedback    = state.get("human_feedback")
    targeted_epic_ids = state.get("targeted_epic_ids") or []
    existing_epics    = state.get("epics", [])

    print(
        f"[epics] Phase 2 | projet={project_id}"
        f" | feedback={'oui' if human_feedback else 'non'}"
        f" | cible={len(targeted_epic_ids)} | existants={len(existing_epics)}"
    )

    if not cdc_text:
        return {"error": "cdc_text vide — phase extraction non terminee.", "current_phase": "epics"}

    # CAS 3 : rejet cible — corriger uniquement les epics selectionnes
    if human_feedback and targeted_epic_ids and project_id:
        print(f"[epics] Rejet cible -> {len(targeted_epic_ids)} epics a corriger")
        try:
            epics = await _targeted_regen(project_id, targeted_epic_ids, cdc_text, human_feedback)
        except Exception as e:
            print(f"[epics] ERREUR targeted_regen : {type(e).__name__}: {str(e)[:200]}")
            epics = await _reload_epics(project_id)
        return _done(epics)

    # CAS 2 : rejet global — modifier les epics existants selon le feedback
    if human_feedback and existing_epics and project_id:
        print("[epics] Rejet global -> improve_all_epics (garde les db_ids existants)")
        try:
            epics = await _global_regen(project_id, existing_epics, cdc_text, human_feedback)
        except Exception as e:
            print(f"[epics] ERREUR global_regen : {type(e).__name__}: {str(e)[:200]}")
            epics = await _reload_epics(project_id)
        return _done(epics)

    # CAS 1 : premiere generation depuis le CDC
    try:
        epics = await generate_epics(cdc_text, human_feedback)
    except Exception as e:
        error_msg = str(e)
        print(f"[epics] ERREUR : {type(e).__name__}: {error_msg[:200]}")
        return {
            "epics": [], "error": error_msg, "current_phase": "epics",
            "validation_status": "pending_human", "human_feedback": None,
            "targeted_epic_ids": None, "targeted_story_ids": None,
        }

    print(f"[epics] {len(epics)} epics generes")

    if project_id:
        await save_epics(project_id, epics)
        print(f"[epics] {len(epics)} epics persistes en base")

    return _done(epics)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _done(epics: list[dict]) -> dict:
    return {
        "epics":              epics,
        "current_phase":      "epics",
        "validation_status":  "pending_human",
        "human_feedback":     None,
        "targeted_epic_ids":  None,
        "targeted_story_ids": None,
        "error":              None,
    }


async def _reload_epics(project_id: int) -> list[dict]:
    """Recharge les epics depuis la DB et retourne des dicts sans db_id."""
    db_epics = await get_epics(project_id)
    return [
        {"title": e.title, "description": e.description or "",
         "splitting_strategy": e.splitting_strategy}
        for e in db_epics
    ]


async def _apply_improved_epics(
    project_id: int,
    improved: list[dict],
    original_db_ids: list[int] | None = None,
) -> list[dict]:
    """
    Applique les epics retournés par le LLM en base :
    - db_id existant → UPDATE
    - db_id None     → INSERT (scission ou nouvel epic)
    - db_id absent du retour LLM (vs original_db_ids) → DELETE (+ cascade stories)
    Retourne la liste complète des epics depuis la DB.
    """
    returned_db_ids = {e["db_id"] for e in improved if e.get("db_id")}

    # Suppressions : epics présents avant mais absents du retour LLM
    if original_db_ids:
        for db_id in original_db_ids:
            if db_id not in returned_db_ids:
                await delete_epic(db_id)
                print(f"[epics] DELETE epic {db_id} (!!!!!!!!!!!!supprime par le PM !!!!!!)")

    # Mises à jour et insertions
    for e in improved:
        payload = {
            "title":              e["title"],
            "description":        e.get("description", ""),
            "splitting_strategy": e.get("splitting_strategy", "by_feature"),
        }
        if e.get("db_id"):
            await update_epic(e["db_id"], payload)
            print(f"[epics] UPDATE epic {e['db_id']} -> {e['title'][:50]}")
        else:
            new_e = await add_epic(project_id, payload)
            print(f"[epics] INSERT nouvel epic -> {e['title'][:50]} (id={new_e.id})")

    return await _reload_epics(project_id)


async def _targeted_regen(
    project_id: int,
    targeted_epic_ids: list[int],
    cdc_text: str,
    feedback: str,
) -> list[dict]:
    """Rejet ciblé : améliore uniquement les epics sélectionnés."""
    db_epics = await get_epics(project_id)
    epics_to_fix = [
        {
            "db_id":              e.id,
            "title":              e.title,
            "description":        e.description or "",
            "splitting_strategy": e.splitting_strategy,
        }
        for e in db_epics
        if e.id in targeted_epic_ids
    ]

    if not epics_to_fix:
        print("[epics]  !!! Aucun epic trouve pour les IDs cibles -> skip")
        return await _reload_epics(project_id)

    print(f"[epics] Cibles : {[e['title'][:40] for e in epics_to_fix]}")
    improved = await improve_targeted_epics(epics_to_fix, cdc_text, feedback)
    return await _apply_improved_epics(project_id, improved, targeted_epic_ids)


async def _global_regen(
    project_id: int,
    existing_epics_state: list[dict],
    cdc_text: str,
    feedback: str,
) -> list[dict]:
    """Rejet global : passe tous les epics existants au LLM pour modification ciblée."""
    db_epics = await get_epics(project_id)

    # Enrichir les epics state avec leur db_id depuis la DB (même ordre)
    epics_with_db_id = []
    for i, e in enumerate(existing_epics_state):
        db_id = db_epics[i].id if i < len(db_epics) else None
        epics_with_db_id.append({
            "db_id":              db_id,
            "title":              e.get("title", ""),
            "description":        e.get("description", ""),
            "splitting_strategy": e.get("splitting_strategy", "by_feature"),
        })

    original_db_ids = [e["db_id"] for e in epics_with_db_id if e.get("db_id")]
    improved = await improve_all_epics(epics_with_db_id, cdc_text, feedback)
    return await _apply_improved_epics(project_id, improved, original_db_ids)
