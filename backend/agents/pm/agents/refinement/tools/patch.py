# agents/pm/agents/refinement/tools/patch.py
# ═══════════════════════════════════════════════════════════════
# Logique Python pure — Application des patches sur les stories
#
# Aucun LLM ici : merge + apply sont déterministes.
# Un patch = { story_local_idx, field, ... }
# story_local_idx : index de la story dans le groupe epic (0-based)
# ═══════════════════════════════════════════════════════════════

import json

_FIBONACCI = {1, 2, 3, 5, 8}

_MAJOR_FIELDS = {"title", "story_points"}   # champs dont le changement compte pour le consensus


def merge_patches(po_patches: list[dict], tech_patches: list[dict]) -> list[dict]:
    """Fusionne les patches PO et TL.
    En cas de conflit sur story_points : on prend la valeur la plus haute (prudence technique).
    """
    merged: dict[tuple, dict] = {}

    for patch in po_patches + tech_patches:
        idx   = patch.get("story_local_idx", -1)
        field = patch.get("field", "")
        key   = (idx, field)

        if key not in merged:
            merged[key] = patch
        elif field == "story_points":
            # Conflit SP : on garde la valeur la plus haute
            merged[key]["new_value"] = max(
                merged[key].get("new_value", 0),
                patch.get("new_value", 0),
            )
            merged[key]["reason"] += f" | TL: {patch.get('reason', '')}"
        elif field == "acceptance_criteria" and patch.get("action") == "add":
            # AC à ajouter : on cumule (pas de conflit)
            merged[key] = patch
        # Sinon : premier patch gagne (PO prioritaire)

    return list(merged.values())


def _capture_old_value(story: dict, field: str):
    """Capture la valeur actuelle d'un champ avant application du patch."""
    if field == "title":
        return story.get("title", "")
    if field == "description":
        return story.get("description", "")
    if field == "story_points":
        return story.get("story_points")
    if field == "acceptance_criteria":
        return _parse_ac(story.get("acceptance_criteria", []))
    return None


def _apply_field_patch(story: dict, field: str, patch: dict) -> dict:
    """Applique un patch sur un seul champ d'une story (copie déjà faite)."""
    if field == "title":
        new_val = patch.get("new_value", "")
        if new_val and isinstance(new_val, str):
            story["title"] = new_val

    elif field == "description":
        new_val = patch.get("new_value", "")
        if new_val and isinstance(new_val, str):
            story["description"] = new_val

    elif field == "story_points":
        new_val = patch.get("new_value")
        if isinstance(new_val, (int, float)):
            sp = int(new_val)
            story["story_points"] = min(_FIBONACCI, key=lambda x: abs(x - sp))

    elif field == "acceptance_criteria":
        action  = patch.get("action", "add")
        current = _parse_ac(story.get("acceptance_criteria", []))
        if action == "add":
            val = patch.get("value", "")
            if val and val not in current:
                current.append(val)
        elif action == "remove":
            idx_to_remove = patch.get("criterion_idx")
            if isinstance(idx_to_remove, int) and 0 <= idx_to_remove < len(current):
                current.pop(idx_to_remove)
        elif action == "replace":
            new_list = patch.get("value", [])
            if isinstance(new_list, list):
                current = new_list
        story["acceptance_criteria"] = current

    return story


def apply_patches(
    stories: list[dict],
    epic_id: int,
    patches: list[dict],
) -> list[dict]:
    """Applique les patches sur les stories d'un epic donné.
    Retourne la liste complète mise à jour (les autres stories sont inchangées).
    """
    epic_indices = [i for i, s in enumerate(stories) if s.get("epic_id") == epic_id]

    # ── [DEBUG] table de correspondance local→global→db_id ───────
    print(f"  [apply_patches] epic_id={epic_id} | {len(epic_indices)} stories dans cet epic")
    for local_i, global_i in enumerate(epic_indices):
        s = stories[global_i]
        print(f"  [apply_patches]   local[{local_i}] → global[{global_i}] → db_id={s.get('db_id')} | '{str(s.get('title',''))[:35]}'")

    for patch in patches:
        local_idx = patch.get("story_local_idx")
        field     = patch.get("field", "")

        if local_idx is None or field == "flag":
            continue

        if local_idx >= len(epic_indices):
            print(f"  [apply_patches] ⚠ local_idx={local_idx} hors-limites → ignoré")
            continue

        global_idx = epic_indices[local_idx]
        story      = dict(stories[global_idx])

        print(f"  [apply_patches] PATCH local[{local_idx}]→global[{global_idx}]→db_id={story.get('db_id')} | field={field} | new_value={str(patch.get('new_value',''))[:40]}")

        story   = _apply_field_patch(story, field, patch)
        stories = stories[:global_idx] + [story] + stories[global_idx + 1:]

    return stories


def apply_patches_enriched(
    stories: list[dict],
    epic_id: int,
    patches: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Comme apply_patches mais retourne aussi les patches enrichis avec :
      - old_value : valeur AVANT le patch
      - new_value_applied : valeur APRÈS (réelle, après Fibonacci clamp etc.)
      - db_id / epic_id : pour que le frontend identifie la story sans ambiguïté
    Utilisé pour l'UI de validation round-by-round.
    """
    epic_indices = [i for i, s in enumerate(stories) if s.get("epic_id") == epic_id]
    enriched: list[dict] = []

    for patch in patches:
        local_idx = patch.get("story_local_idx")
        field     = patch.get("field", "")

        if local_idx is None or field == "flag":
            enriched.append({**patch, "db_id": None, "applied": False})
            continue

        if local_idx >= len(epic_indices):
            continue

        global_idx = epic_indices[local_idx]
        story      = dict(stories[global_idx])

        old_value = _capture_old_value(story, field)
        story     = _apply_field_patch(story, field, patch)

        # Lire la valeur réellement appliquée (après Fibonacci clamp, etc.)
        if field == "story_points":
            new_value_applied = story.get("story_points")
        elif field == "acceptance_criteria":
            new_value_applied = story.get("acceptance_criteria")
        else:
            new_value_applied = patch.get("new_value")

        stories = stories[:global_idx] + [story] + stories[global_idx + 1:]

        enriched.append({
            **patch,
            "old_value":         old_value,
            "new_value_applied": new_value_applied,
            "db_id":             story.get("db_id"),
            "epic_id":           epic_id,
            "applied":           True,
        })

    return stories, enriched


def check_consensus(round_patches: list[dict], major_threshold: int = 2, total_threshold: int = 5) -> bool:
    """Consensus = peu de patches majeurs ET peu de patches au total.

    Évite un faux consensus quand le TL échoue (0 patches TL → majors bas
    mais le problème persiste).

    major_threshold : max patches title/story_points autorisés
    total_threshold : max patches totaux (hors flags) autorisés
    """
    actionable = [p for p in round_patches if p.get("field") != "flag"]
    major = sum(1 for p in actionable if p.get("field") in _MAJOR_FIELDS)
    return major < major_threshold and len(actionable) < total_threshold


def _parse_ac(ac) -> list[str]:
    if isinstance(ac, list):
        return list(ac)
    if isinstance(ac, str):
        try:
            parsed = json.loads(ac)
            return parsed if isinstance(parsed, list) else [ac]
        except (json.JSONDecodeError, ValueError):
            return [ac] if ac else []
    return []
