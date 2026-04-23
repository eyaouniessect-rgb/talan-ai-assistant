# agents/pm/agents/refinement/tools/tech_review.py
# ═══════════════════════════════════════════════════════════════
# Agent Tech Lead — Revue technique des User Stories
#
# Vérifie :
#   1. Story Points : réalisme technique (Fibonacci 1-8)
#   2. Faisabilité en 1 sprint (2 semaines)
#   3. INVEST : Indépendante, Estimable, Small, Testable
#   4. Clarté de la description pour l'implémentation
#   5. Dépendances implicites non mentionnées
# ═══════════════════════════════════════════════════════════════

import asyncio
import json
import re

from app.core.groq_client import invoke_with_fallback

_RETRY_DELAYS = [3, 7]   # secondes avant 1er et 2e retry

_MODEL = "openai/gpt-oss-120b"

_SYSTEM = """Tu es un Tech Lead senior expert en estimation et architecture logicielle.
Tu audites des User Stories du point de vue technique et proposes des corrections précises au format JSON.
Sois pragmatique : ne propose de patch QUE si la correction est vraiment nécessaire.
Maximum 2 patches par story. Réponds UNIQUEMENT avec du JSON valide, sans markdown."""


def _build_prompt(
    epic: dict,
    epic_idx: int,
    stories: list[dict],
    architecture_details: dict | None,
) -> str:
    stories_text = "\n".join([
        f"  [{i}] {s['title']} ({s.get('story_points', '?')} pts)\n"
        f"      Description : {s.get('description', '')[:500]}"
        for i, s in enumerate(stories)
    ])

    arch_section = ""
    if architecture_details:
        layers = architecture_details.get("layers", [])
        if layers:
            arch_section = "\nARCHITECTURE CIBLE :\n" + "\n".join(
                f"  • {l.get('name', '')}: {', '.join(l.get('components', []))}"
                for l in layers
            ) + "\n"

    return f"""Audite ces User Stories en tant que Tech Lead.

══════════════════════════════════════════════
EPIC #{epic_idx} : {epic.get('title', '')}
Description : {epic.get('description', '')[:300]}
{arch_section}══════════════════════════════════════════════

STORIES (index 0..{len(stories)-1}) :
{stories_text}

══════════════════════════════════════════════
CRITÈRES D'AUDIT TECH LEAD
══════════════════════════════════════════════
1. STORY POINTS (Fibonacci 1,2,3,5,8 — 13 interdit) :
   - 1-2 pts : tâche simple, pas de dépendance externe
   - 3-5 pts : complexité normale, quelques intégrations
   - 8 pts   : fonctionnalité complexe, plusieurs composants
   → si SP sous/sur-estimé : patch field="story_points", new_value=N
2. FAISABILITÉ : la story doit tenir dans 1 sprint (2 semaines, 1 dev)
   → si trop grande : patch field="flag", value="too_large"
3. DESCRIPTION : suffisamment précise pour implémenter sans ambiguïté ?
   → si vague : patch field="description", new_value="..."
4. INVEST — Small + Estimable + Testable :
   → si problème : patch field="flag", value="invest_violation"

RÈGLE : propose UNIQUEMENT les patches nécessaires. Ne touche pas ce qui est correct.
Maximum 2 patches par story (index 0..{len(stories)-1}).

Retourne UNIQUEMENT ce JSON :
{{
  "summary": "Une phrase résumant les problèmes techniques.",
  "patches": [
    {{
      "story_local_idx": 0,
      "field": "story_points|description|flag",
      "new_value": 5,
      "value": "...",
      "reason": "Une phrase courte."
    }}
  ]
}}

Si tout est correct : {{"summary": "Aucun problème technique détecté.", "patches": []}}"""


async def run_tech_review(
    epic: dict,
    epic_idx: int,
    stories: list[dict],
    architecture_details: dict | None = None,
) -> tuple[list[dict], str]:
    """
    Revue Tech Lead des stories d'un epic.
    Retourne (patches, summary).
    Fail-safe : si erreur LLM → ([], "Revue TL indisponible").
    """
    if not stories:
        return [], "Aucune story à auditer."

    prompt = _build_prompt(epic, epic_idx, stories, architecture_details)

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

            print(f"[tech_review]  Epic {epic_idx} → {len(patches)} patch(es) TL" +
                  (f" (après {attempt} retry)" if attempt > 0 else ""))
            return patches, summary

        except Exception as e:
            last_error = e
            if attempt < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt]
                print(f"[tech_review] ⚠ Epic {epic_idx} tentative {attempt + 1} échouée ({type(e).__name__}) → retry dans {delay}s")
                await asyncio.sleep(delay)

    print(f"[tech_review] ✗ Epic {epic_idx} — {attempts} tentatives échouées ({type(last_error).__name__}) → fail-safe (0 patches)")
    return [], f"Revue TL indisponible ({type(last_error).__name__})."


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
        if field not in {"story_points", "description", "flag"}:
            continue

        counts[idx] = counts.get(idx, 0) + 1
        if counts[idx] > 2:
            continue

        # Valider new_value pour story_points
        if field == "story_points":
            nv = p.get("new_value")
            if not isinstance(nv, (int, float)) or int(nv) not in {1, 2, 3, 5, 8}:
                continue

        valid.append(p)

    return valid
