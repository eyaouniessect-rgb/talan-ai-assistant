# agents/pm/agents/staffing/steps/profile_extraction/service.py
# ═══════════════════════════════════════════════════════════════
# Step 1 — Profile Extraction
#
# Stratégie d'appel LLM par batch :
#   - Stories découpées en batchs de BATCH_SIZE (25 max)
#   - Batch 1 → NVIDIA clé 1  (nvidia_key_index=0, max_keys=1)
#   - Batch 2 → NVIDIA clé 2  (nvidia_key_index=1, max_keys=1)
#   - Batch N → clé (N-1) — rotation circulaire sur les clés NVIDIA
#   - Tous les batchs tournent en parallèle (asyncio.gather)
#
# Retry par batch :
#   Si NVIDIA échoue → attendre 7s → retry NVIDIA
#   Après RETRY_ATTEMPTS tentatives → RuntimeError (pas de fallback Groq)
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
import asyncio
import json
import re

from agents.pm.agents.staffing.steps.profile_extraction.prompt import (
    PROFILE_EXTRACTION_SYSTEM_PROMPT,
    build_profile_extraction_prompt,
)
from agents.pm.agents.staffing.schemas import (
    ProfileExtractionResult,
    StoryProfileRequirement,
)
from app.core.groq_client import invoke_with_fallback

_MODEL              = "openai/gpt-oss-120b"
_BATCH_SIZE         = 25    # stories par appel LLM
_MAX_TOKENS         = 6000  # output tokens par batch (25 stories × ~250 tokens ≈ 6 250)
_RETRY_ATTEMPTS     = 3     # tentatives NVIDIA par batch
_NVIDIA_RETRY_DELAY = 7     # secondes d'attente entre deux tentatives NVIDIA
_VALID_LEVELS       = {"JUNIOR", "MID", "SENIOR"}


# ──────────────────────────────────────────────────────────────
# Normalisation
# ──────────────────────────────────────────────────────────────

def _normalize_level(raw: str | None) -> str:
    if not raw:
        return "MID"
    upper = str(raw).upper().strip()
    return upper if upper in _VALID_LEVELS else "MID"


def _normalize_string_list(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _parse_batch_response(raw: str, expected_ids: list[int]) -> list[StoryProfileRequirement]:
    """
    Parse la réponse JSON d'un batch.
    Les stories absentes de la réponse reçoivent un fallback.
    """
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    data  = json.loads(clean)

    raw_profiles = data.get("stories_profiles", [])
    if not isinstance(raw_profiles, list):
        raise ValueError("Le champ 'stories_profiles' doit être une liste.")

    seen_ids:  set[int]                      = set()
    validated: list[StoryProfileRequirement] = []

    for entry in raw_profiles:
        if not isinstance(entry, dict):
            continue
        story_id = entry.get("story_id")
        if story_id is None:
            continue
        try:
            story_id = int(story_id)
        except (TypeError, ValueError):
            continue
        if story_id in seen_ids:
            continue
        seen_ids.add(story_id)

        profiles = _normalize_string_list(entry.get("required_profiles", []))
        skills   = _normalize_string_list(entry.get("required_skills",   []))
        level    = _normalize_level(entry.get("required_level"))

        if not profiles:
            profiles = ["Full Stack Developer"]
        if not skills:
            skills = ["Software Development"]

        validated.append(StoryProfileRequirement(
            story_id          = story_id,
            required_profiles = profiles,
            required_skills   = skills,
            required_level    = level,
        ))

    # Fallback pour les stories absentes de la réponse LLM
    missing = set(expected_ids) - seen_ids
    for sid in missing:
        print(f"[profile_extraction] ⚠️  story_id={sid} absent → fallback")
        validated.append(StoryProfileRequirement(
            story_id          = sid,
            required_profiles = ["Full Stack Developer"],
            required_skills   = ["Software Development"],
            required_level    = "MID",
        ))

    return validated


# ──────────────────────────────────────────────────────────────
# Appel NVIDIA pour un batch — retry avec délai, pas de Groq
# ──────────────────────────────────────────────────────────────

async def _call_nvidia_batch(
    user_prompt:      str,
    batch_index:      int,
    nvidia_key_index: int,
) -> str:
    """
    Appelle NVIDIA pour un batch avec retry.

    Séquence :
      tentative 1 → NVIDIA clé nvidia_key_index
      échec       → attendre 7s
      tentative 2 → NVIDIA clé nvidia_key_index
      échec       → attendre 7s
      tentative 3 → NVIDIA clé nvidia_key_index
      échec       → RuntimeError (pas de fallback Groq)
    """
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            raw = await invoke_with_fallback(
                model            = _MODEL,
                messages         = [
                    {"role": "system", "content": PROFILE_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens       = _MAX_TOKENS,
                temperature      = 0,
                nvidia_key_index = nvidia_key_index,
                nvidia_max_keys  = 1,       # une seule clé par batch — pas de rotation
                skip_groq        = True,    # pas de fallback Groq
            )
            if not raw or not raw.strip():
                raise ValueError("Réponse NVIDIA vide")

            print(f"[profile_extraction] ✅ Batch {batch_index} NVIDIA clé #{nvidia_key_index + 1} OK (tentative {attempt})")
            return raw

        except Exception as e:
            print(
                f"[profile_extraction] ⚠️  Batch {batch_index} tentative {attempt}/{_RETRY_ATTEMPTS} "
                f"NVIDIA clé #{nvidia_key_index + 1} échouée : {type(e).__name__}: {str(e)[:80]}"
            )
            if attempt < _RETRY_ATTEMPTS:
                print(f"[profile_extraction] Batch {batch_index} → attente {_NVIDIA_RETRY_DELAY}s avant retry...")
                await asyncio.sleep(_NVIDIA_RETRY_DELAY)

    raise RuntimeError(
        f"[profile_extraction] Batch {batch_index} : NVIDIA clé #{nvidia_key_index + 1} "
        f"a échoué après {_RETRY_ATTEMPTS} tentatives."
    )


# ──────────────────────────────────────────────────────────────
# Traitement complet d'un batch (appel + parsing)
# ──────────────────────────────────────────────────────────────

async def _process_batch(
    batch:            list[dict],
    batch_index:      int,
    nvidia_key_index: int,
    feedback:         str | None,
) -> list[StoryProfileRequirement]:
    """
    Appelle NVIDIA pour un batch et parse le résultat.
    En cas d'erreur de parsing → fallback pour toutes les stories du batch.
    """
    expected_ids = [s["story_id"] for s in batch]
    print(
        f"[profile_extraction] Batch {batch_index} | {len(batch)} stories "
        f"| NVIDIA clé #{nvidia_key_index + 1}"
    )

    user_prompt  = build_profile_extraction_prompt(batch, human_feedback=feedback)
    raw_response = await _call_nvidia_batch(user_prompt, batch_index, nvidia_key_index)

    try:
        return _parse_batch_response(raw_response, expected_ids)
    except (json.JSONDecodeError, ValueError) as e:
        print(
            f"[profile_extraction] ⚠️  Batch {batch_index} réponse non parseable ({e}) "
            f"→ fallback pour les {len(batch)} stories"
        )
        return [
            StoryProfileRequirement(
                story_id          = s["story_id"],
                required_profiles = ["Full Stack Developer"],
                required_skills   = ["Software Development"],
                required_level    = "MID",
            )
            for s in batch
        ]


# ──────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────

async def extract_profiles(
    stories:  list[dict],
    feedback: str | None = None,
) -> ProfileExtractionResult:
    """
    Extrait les profils requis pour toutes les stories.

    Stratégie :
      - Découpe en batchs de _BATCH_SIZE stories (10 max)
      - Exécution SÉQUENTIELLE batch par batch (évite la surcharge NVIDIA)
      - Rotation des clés NVIDIA : batch 1→clé 0, batch 2→clé 1, batch 3→clé 0, …
      - Si NVIDIA échoue : 7s de délai + retry (_RETRY_ATTEMPTS fois)
      - Pas de fallback Groq

    stories  : chaque dict contient story_id, title, description, story_points
    feedback : correction PM (rejet) — injectée dans le prompt
    """
    if not stories:
        return ProfileExtractionResult(stories_profiles=[])

    batches   = [stories[i: i + _BATCH_SIZE] for i in range(0, len(stories), _BATCH_SIZE)]
    n_batches = len(batches)
    print(
        f"[profile_extraction] {len(stories)} stories → "
        f"{n_batches} batch(s) de ≤{_BATCH_SIZE} | séquentiel"
    )

    # Exécution séquentielle avec rotation des clés NVIDIA
    merged: list[StoryProfileRequirement] = []
    for i, batch in enumerate(batches):
        nvidia_key_index = i % 2   # rotation : clé 0, clé 1, clé 0, clé 1, …
        batch_result = await _process_batch(
            batch            = batch,
            batch_index      = i + 1,
            nvidia_key_index = nvidia_key_index,
            feedback         = feedback,
        )
        merged.extend(batch_result)

    fallback_count = sum(
        1 for r in merged
        if r.required_profiles == ["Full Stack Developer"]
        and r.required_skills  == ["Software Development"]
    )
    print(
        f"[profile_extraction] ✅ {len(merged)} profils extraits "
        f"({fallback_count} fallbacks)"
    )

    return ProfileExtractionResult(stories_profiles=merged)
