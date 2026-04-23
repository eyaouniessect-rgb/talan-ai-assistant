# agents/pm/agents/refinement/service.py
# ═══════════════════════════════════════════════════════════════
# Orchestrateur déterministe — Phase 4 Raffinement PO ↔ Tech Lead
#
# Boucle max 3 rounds :
#   Pour chaque round :
#     Pour chaque epic :
#       PO review + TL review (en PARALLÈLE asyncio.gather)
#       → merge des patches (Python pur)
#       → apply patches sur les stories
#     Consensus = moins de 3 patches majeurs (title, story_points) dans le round
#     Sortie anticipée si consensus atteint
# ═══════════════════════════════════════════════════════════════

import asyncio

from agents.pm.agents.refinement.tools.po_review   import run_po_review
from agents.pm.agents.refinement.tools.tech_review import run_tech_review
from agents.pm.agents.refinement.tools.patch       import merge_patches, apply_patches, apply_patches_enriched, check_consensus

MAX_ROUNDS = 3


def _build_already_patched(previous_rounds: list[dict]) -> set[tuple]:
    """
    Construit l'ensemble des (db_id, field) déjà patchés dans les rounds précédents.
    Permet de filtrer les re-patches redondants dans le round courant.
    """
    seen: set[tuple] = set()
    for r in previous_rounds:
        for p in r.get("stories_patch", []):
            db_id = p.get("db_id")
            field = p.get("field")
            if db_id and field and field != "flag":
                seen.add((db_id, field))
    return seen


def _filter_new_patches(patches: list[dict], already_patched: set[tuple]) -> list[dict]:
    """
    Supprime les patches sur des (db_id, field) déjà traités dans un round précédent.
    Évite que le LLM re-propose indéfiniment les mêmes corrections.
    """
    filtered = []
    skipped  = 0
    for p in patches:
        db_id = p.get("db_id")
        field = p.get("field")
        if db_id and field and (db_id, field) in already_patched:
            skipped += 1
            print(f"  [filter] skip re-patch db_id={db_id} field={field} (déjà corrigé)")
            continue
        filtered.append(p)
    if skipped:
        print(f"  [filter] {skipped} re-patch(es) ignoré(s) sur ce round")
    return filtered


async def run_one_round(
    stories:              list[dict],
    epics:                list[dict],
    round_number:         int,
    architecture_details: dict | None = None,
    previous_rounds:      list[dict]  = None,
) -> tuple[list[dict], dict]:
    """
    Exécute UN seul round PO↔TL.

    previous_rounds : rounds déjà appliqués — utilisés pour filtrer les re-patches.
    Retourne (stories_après_round, round_data).
    """
    current_stories  = list(stories)
    round_patches:   list[dict] = []
    po_summaries:    list[str]  = []
    tl_summaries:    list[str]  = []

    # Ensemble des (db_id, field) déjà patchés dans les rounds précédents
    already_patched  = _build_already_patched(previous_rounds or [])

    print(f"\n[refinement] ┌─ ROUND {round_number} (run_one_round) {'─'*40}")
    if already_patched:
        print(f"[refinement] │  {len(already_patched)} (db_id, field) déjà patchés → seront ignorés")

    for epic_idx, epic in enumerate(epics):
        epic_stories = [s for s in current_stories if s.get("epic_id") == epic_idx]
        if not epic_stories:
            continue

        print(f"[refinement] │  Epic {epic_idx} — {len(epic_stories)} stories")
        for local_i, s in enumerate(epic_stories):
            print(f"[refinement] │    [{local_i}] db_id={s.get('db_id')} | {str(s.get('title',''))[:40]}")

        (po_patches, po_summary), (tl_patches, tl_summary) = await asyncio.gather(
            run_po_review(epic, epic_idx, epic_stories),
            run_tech_review(epic, epic_idx, epic_stories, architecture_details),
        )

        print(f"[refinement] │    PO={len(po_patches)} patches | TL={len(tl_patches)} patches (avant filtre)")
        po_summaries.append(f"Epic {epic_idx}: {po_summary}")
        tl_summaries.append(f"Epic {epic_idx}: {tl_summary}")

        epic_patches = merge_patches(po_patches, tl_patches)

        # apply_patches_enriched : capture old_value + db_id pour le diff
        current_stories, enriched = apply_patches_enriched(current_stories, epic_idx, epic_patches)

        # Filtrer les re-patches déjà appliqués dans les rounds précédents
        enriched_new = _filter_new_patches(enriched, already_patched)
        round_patches.extend(enriched_new)

    consensus = check_consensus(round_patches)
    actionable = [p for p in round_patches if p.get("field") != "flag"]
    major      = sum(1 for p in actionable if p.get("field") in {"title", "story_points"})

    print(f"[refinement] └─ Round {round_number} : {len(round_patches)} patches | actionable={len(actionable)} | majeurs={major} | consensus={'✓' if consensus else '✗'}")

    round_data = {
        "round":         round_number,
        "patches_count": len(round_patches),
        "consensus":     consensus,
        "po_comment":    " | ".join(po_summaries),
        "tech_comment":  " | ".join(tl_summaries),
        "stories_patch": round_patches,   # enrichis avec old_value + db_id
    }

    return current_stories, round_data


async def run_refinement(
    stories:             list[dict],
    epics:               list[dict],
    human_feedback:      str | None  = None,
    architecture_details: dict | None = None,
    project_id:          int | None  = None,
) -> tuple[list[dict], list[dict]]:
    """
    Raffine les stories via max {MAX_ROUNDS} rounds PO ↔ Tech Lead.

    Retourne :
      (refined_stories, refinement_rounds)

    refinement_rounds : liste des rounds avec patches et résumés PO/TL.
    """
    current_stories = list(stories)
    all_rounds: list[dict] = []

    # ── [DEBUG] inventaire initial des stories avec db_id ────────
    print(f"\n{'='*60}")
    print(f"[refinement] ▶ DÉMARRAGE projet={project_id}")
    print(f"[refinement]   {len(stories)} stories | {len(epics)} epics")
    print(f"[refinement]   Stories reçues (local_pos → db_id | epic_id | title[:40]) :")
    for pos, s in enumerate(stories):
        print(f"              [{pos:02d}] db_id={s.get('db_id')} | epic={s.get('epic_id')} | {str(s.get('title',''))[:40]}")
    print(f"{'='*60}")

    for round_idx in range(MAX_ROUNDS):
        round_patches: list[dict] = []
        po_summaries:  list[str]  = []
        tl_summaries:  list[str]  = []

        print(f"\n[refinement] ┌─ ROUND {round_idx + 1}/{MAX_ROUNDS} {'─'*45}")

        for epic_idx, epic in enumerate(epics):
            epic_stories = [s for s in current_stories if s.get("epic_id") == epic_idx]
            if not epic_stories:
                continue

            # ── [DEBUG] stories envoyées au LLM avec leur db_id ──
            print(f"[refinement] │  Epic {epic_idx} — '{str(epic.get('title',''))[:35]}' — {len(epic_stories)} stories")
            print(f"[refinement] │    local_idx → db_id  | title[:35]")
            for local_i, s in enumerate(epic_stories):
                print(f"[refinement] │    [{local_i}]        → db_id={s.get('db_id')} | {str(s.get('title',''))[:35]}")

            # PO + TL en parallèle — même input, analyses indépendantes
            (po_patches, po_summary), (tl_patches, tl_summary) = await asyncio.gather(
                run_po_review(epic, epic_idx, epic_stories),
                run_tech_review(epic, epic_idx, epic_stories, architecture_details),
            )

            # ── [DEBUG] patches reçus de chaque reviewer ─────────
            print(f"[refinement] │    PO  → {len(po_patches)} patch(es) : {[{'idx':p.get('story_local_idx'),'field':p.get('field')} for p in po_patches]}")
            print(f"[refinement] │    TL  → {len(tl_patches)} patch(es) : {[{'idx':p.get('story_local_idx'),'field':p.get('field')} for p in tl_patches]}")

            po_summaries.append(f"Epic {epic_idx}: {po_summary}")
            tl_summaries.append(f"Epic {epic_idx}: {tl_summary}")

            # Fusion puis application
            epic_patches    = merge_patches(po_patches, tl_patches)

            # ── [DEBUG] patches fusionnés avant apply ─────────────
            print(f"[refinement] │    Merged → {len(epic_patches)} patch(es) appliqués sur epic {epic_idx}")

            current_stories = apply_patches(current_stories, epic_idx, epic_patches)
            round_patches.extend(epic_patches)

        consensus = check_consensus(round_patches)

        # ── [DEBUG] bilan du round ────────────────────────────────
        actionable = [p for p in round_patches if p.get("field") != "flag"]
        major      = sum(1 for p in actionable if p.get("field") in {"title", "story_points"})
        print(f"[refinement] └─ Round {round_idx + 1} terminé :")
        print(f"[refinement]    patches total={len(round_patches)} | actionable={len(actionable)} | majeurs={major}")
        print(f"[refinement]    consensus={'✓ OUI' if consensus else '✗ NON (round suivant)'}")

        all_rounds.append({
            "round":          round_idx + 1,
            "patches_count":  len(round_patches),
            "consensus":      consensus,
            "po_comment":     " | ".join(po_summaries),
            "tech_comment":   " | ".join(tl_summaries),
            "stories_patch":  round_patches,
        })

        if consensus:
            print(f"[refinement] ✓ Consensus atteint au round {round_idx + 1} → arrêt")
            break

    # ── [DEBUG] état final des stories après tous les rounds ──────
    print(f"\n[refinement] ═══ ÉTAT FINAL après {len(all_rounds)} round(s) ═══")
    print(f"[refinement]   Stories finales (db_id | sp | title[:40]) :")
    for s in current_stories:
        print(f"              db_id={s.get('db_id')} | sp={s.get('story_points')} | {str(s.get('title',''))[:40]}")
    print(f"[refinement] ══════════════════════════════════════════════════\n")

    return current_stories, all_rounds
