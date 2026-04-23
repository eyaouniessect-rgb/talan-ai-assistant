# agents/pm/agents/refinement/tools/po_review.py
# ═══════════════════════════════════════════════════════════════
# Agent PO — Revue métier des User Stories
#
# Vérifie :
#   1. Format "En tant que [rôle], je veux [action] afin de [bénéfice]"
#   2. Valeur métier claire et mesurable
#   3. Critères d'acceptation : testables, cas négatif présent
#   4. Scope : la story reste dans le périmètre de l'epic
#   5. Granularité : la story n'est pas trop large (> 8 pts = à découper)
# ═══════════════════════════════════════════════════════════════

import asyncio
import json
import re

from app.core.groq_client import invoke_with_fallback

_RETRY_DELAYS = [3, 7]   # secondes avant 1er et 2e retry

_MODEL = "openai/gpt-oss-120b"

_SYSTEM = """Tu es un Product Owner senior expert en rédaction Agile.
Tu audites des User Stories et proposes des corrections précises au format JSON.
Sois pragmatique : ne propose de patch QUE si la correction est vraiment nécessaire.
Maximum 2 patches par story. Réponds UNIQUEMENT avec du JSON valide, sans markdown."""


def _build_prompt(epic: dict, epic_idx: int, stories: list[dict]) -> str:
    stories_text = "\n".join([
        f"  [{i}] {s['title']} ({s.get('story_points', '?')} pts)\n"
        f"      Description : {s.get('description', '')[:500]}\n"
        f"      AC : {'; '.join((s.get('acceptance_criteria') or ['—'])[:3])}"
        for i, s in enumerate(stories)
    ])

    return f"""Audite ces User Stories en tant que Product Owner.

══════════════════════════════════════════════
EPIC #{epic_idx} : {epic.get('title', '')}
Description : {epic.get('description', '')[:300]}
══════════════════════════════════════════════

STORIES (index 0..{len(stories)-1}) :
{stories_text}

══════════════════════════════════════════════
CRITÈRES D'AUDIT PO
══════════════════════════════════════════════
1. FORMAT : "En tant que [rôle précis], je veux [action concrète] afin de [bénéfice métier]"
   → si le format est mauvais : patch field="title"
2. VALEUR : le bénéfice métier est-il clair ? Sinon : patch field="description"
3. AC : au moins 1 critère négatif (token expiré, données invalides, erreur réseau…)
   → si manquant : patch field="acceptance_criteria", action="add"
4. SCOPE : la story reste-t-elle dans le périmètre de l'epic ?
   → si hors périmètre : patch field="flag", value="scope_creep"
5. GRANULARITÉ : une story > 8 pts doit être découpée
   → si trop large : patch field="flag", value="too_large"

RÈGLE : propose UNIQUEMENT les patches nécessaires. Ne touche pas ce qui est correct.
Maximum 2 patches par story (index 0..{len(stories)-1}).

Retourne UNIQUEMENT ce JSON :
{{
  "summary": "Une phrase résumant les problèmes principaux.",
  "patches": [
    {{
      "story_local_idx": 0,
      "field": "title|description|story_points|acceptance_criteria|flag",
      "new_value": "...",
      "action": "add|remove|replace",
      "value": "...",
      "reason": "Une phrase courte."
    }}
  ]
}}

Si tout est correct : {{"summary": "Aucun problème détecté.", "patches": []}}"""


async def run_po_review(
    epic: dict,
    epic_idx: int,
    stories: list[dict],
) -> tuple[list[dict], str]:
    """
    Revue PO des stories d'un epic.
    Retourne (patches, summary).
    Fail-safe : si erreur LLM → ([], "Revue PO indisponible").
    """
    if not stories:
        return [], "Aucune story à auditer."

    prompt = _build_prompt(epic, epic_idx, stories)

    last_error: Exception | None = None
    attempts = 1 + len(_RETRY_DELAYS)

    for attempt in range(attempts):
        try:
            raw = await invoke_with_fallback(
                model      = _MODEL,
                messages   = [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens  = 4096,
                temperature = 0,
            )

            if not raw or not raw.strip():
                raise ValueError("Réponse vide du LLM")

            clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            data  = json.loads(clean)

            patches = _validate_patches(data.get("patches", []), len(stories))
            summary = str(data.get("summary", ""))

            print(f"[po_review]   Epic {epic_idx} → {len(patches)} patch(es) PO" +
                  (f" (après {attempt} retry)" if attempt > 0 else ""))
            return patches, summary

        except Exception as e:
            last_error = e
            if attempt < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt]
                print(f"[po_review] ⚠ Epic {epic_idx} tentative {attempt + 1} échouée ({type(e).__name__}) → retry dans {delay}s")
                await asyncio.sleep(delay)

    print(f"[po_review] ✗ Epic {epic_idx} — {attempts} tentatives échouées ({type(last_error).__name__}) → fail-safe (0 patches)")
    return [], f"Revue PO indisponible ({type(last_error).__name__})."


def _validate_patches(raw_patches: list, nb_stories: int) -> list[dict]:
    """Filtre les patches malformés ou hors-limites."""
    valid  = []
    counts: dict[int, int] = {}

    for p in raw_patches:
        if not isinstance(p, dict):
            continue

        idx = p.get("story_local_idx")
        if not isinstance(idx, int) or idx < 0 or idx >= nb_stories:
            continue

        field = p.get("field", "")
        if field not in {"title", "description", "story_points", "acceptance_criteria", "flag"}:
            continue

        # Max 2 patches par story
        counts[idx] = counts.get(idx, 0) + 1
        if counts[idx] > 2:
            continue

        valid.append(p)

    return valid
