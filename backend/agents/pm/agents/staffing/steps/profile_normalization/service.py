# agents/pm/agents/staffing/steps/profile_normalization/service.py

from __future__ import annotations
import asyncio
import json
import re

from agents.pm.agents.staffing.steps.profile_normalization.prompt import (
    NORMALIZATION_SYSTEM_PROMPT,
    build_normalization_prompt,
)
from agents.pm.agents.staffing.schemas import ProfileMapping, ProfileNormalizationResult
from app.core.groq_client import invoke_with_fallback

_MODEL              = "openai/gpt-oss-120b"
_MAX_TOKENS         = 2000
_RETRY_ATTEMPTS     = 3
_NVIDIA_RETRY_DELAY = 7
_VALID_MATCH_TYPES  = {"exact", "close", "none"}


def _normalize_str(s: str) -> str:
    """Normalise une chaîne : strip, lowercase, espaces multiples → simple."""
    return " ".join(s.strip().split()).lower()


def _apply_exact_override(
    mappings: list[ProfileMapping],
) -> list[ProfileMapping]:
    """
    Post-processing déterministe :
    - Si required_profile est présent (insensible à la casse) dans matched_job_titles
      → forcer match_type="exact", confidence=1.0
    - Si matched_job_titles est vide
      → forcer match_type="none", confidence=0.0
    - Sinon (close)
      → s'assurer que confidence < 1.0 et match_type="close"
    """
    result = []
    for m in mappings:
        profile_norm = _normalize_str(m.required_profile)
        titles_norm  = [_normalize_str(t) for t in m.matched_job_titles]

        if not m.matched_job_titles:
            result.append(m.model_copy(update={"match_type": "none", "confidence": 0.0}))
        elif profile_norm in titles_norm:
            result.append(m.model_copy(update={"match_type": "exact", "confidence": 1.0}))
        else:
            # Close match — clamp confidence entre 0.01 et 0.99
            confidence = max(0.01, min(0.99, m.confidence))
            result.append(m.model_copy(update={"match_type": "close", "confidence": confidence}))
    return result


def _extract_unique_profiles(profile_extraction_result: dict) -> list[str]:
    profiles: set[str] = set()
    for story in profile_extraction_result.get("stories_profiles", []):
        for prof in story.get("required_profiles", []):
            if prof and isinstance(prof, str):
                profiles.add(prof.strip())
    result = sorted(profiles)
    print(f"[normalization] profils uniques extraits depuis step 1 : {result}")
    return result


async def _get_job_titles_from_db() -> list[str]:
    from sqlalchemy import select
    from app.database.connection import AsyncSessionLocal
    from app.database.models.hris import Employee, SeniorityEnum

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Employee.job_title)
            .where(
                Employee.job_title.isnot(None),
                Employee.seniority.notin_([
                    SeniorityEnum.LEAD,
                    SeniorityEnum.HEAD,
                    SeniorityEnum.PRINCIPAL,
                ]),
            )
            .distinct()
            .order_by(Employee.job_title)
        )
        titles = [row[0] for row in result.all() if row[0] and row[0].strip()]

    print(f"[normalization] {len(titles)} job_title distincts trouvés en base : {titles}")
    return titles


async def _call_llm(user_prompt: str) -> str:
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            raw = await invoke_with_fallback(
                model            = _MODEL,
                messages         = [
                    {"role": "system", "content": NORMALIZATION_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens       = _MAX_TOKENS,
                temperature      = 0,
                nvidia_key_index = 0,
                nvidia_max_keys  = 1,
                skip_groq        = True,
            )
            if not raw or not raw.strip():
                raise ValueError("Réponse NVIDIA vide")
            print(f"[normalization] ✅ LLM OK (tentative {attempt})")
            return raw

        except Exception as e:
            print(
                f"[normalization] ⚠️  tentative {attempt}/{_RETRY_ATTEMPTS} échouée : "
                f"{type(e).__name__}: {str(e)[:80]}"
            )
            if attempt < _RETRY_ATTEMPTS:
                print(f"[normalization] attente {_NVIDIA_RETRY_DELAY}s avant retry…")
                await asyncio.sleep(_NVIDIA_RETRY_DELAY)

    raise RuntimeError(
        f"[normalization] LLM a échoué après {_RETRY_ATTEMPTS} tentatives."
    )


def _parse_llm_response(
    raw:                  str,
    required_profiles:    list[str],
    available_job_titles: list[str],
) -> list[ProfileMapping]:
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    data  = json.loads(clean)

    raw_mappings = data.get("profile_mappings", [])
    if not isinstance(raw_mappings, list):
        raise ValueError("Le champ 'profile_mappings' doit être une liste.")

    available_lower = {t.lower(): t for t in available_job_titles}
    seen_profiles:  set[str]             = set()
    validated:      list[ProfileMapping] = []

    for entry in raw_mappings:
        if not isinstance(entry, dict):
            continue
        required = entry.get("required_profile", "").strip()
        if not required or required in seen_profiles:
            continue
        seen_profiles.add(required)

        raw_titles = entry.get("matched_job_titles", [])
        valid_titles = []
        for t in raw_titles:
            t_strip = str(t).strip()
            if t_strip in available_job_titles:
                valid_titles.append(t_strip)
            elif t_strip.lower() in available_lower:
                valid_titles.append(available_lower[t_strip.lower()])
            else:
                print(f"[normalization] ⚠️  '{t_strip}' rejeté — absent de la base")

        match_type = entry.get("match_type", "none")
        if match_type not in _VALID_MATCH_TYPES:
            match_type = "close" if valid_titles else "none"

        try:
            confidence = float(entry.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0

        validated.append(ProfileMapping(
            required_profile   = required,
            matched_job_titles = valid_titles,
            match_type         = match_type,
            confidence         = confidence,
            reason             = str(entry.get("reason", "")),
        ))

    # Fallback pour les profils oubliés par le LLM
    missing = set(required_profiles) - seen_profiles
    for prof in sorted(missing):
        print(f"[normalization] ⚠️  '{prof}' absent de la réponse LLM → fallback none")
        validated.append(ProfileMapping(
            required_profile   = prof,
            matched_job_titles = [],
            match_type         = "none",
            confidence         = 0.0,
            reason             = "Profil non traité par le LLM.",
        ))

    return validated


async def normalize_profiles(
    profile_extraction_result: dict,
) -> ProfileNormalizationResult:
    print("[normalization] ▶ démarrage du step 2 — Profile Normalization")

    required_profiles = _extract_unique_profiles(profile_extraction_result)
    if not required_profiles:
        print("[normalization] ⚠️  aucun profil requis trouvé — résultat vide")
        return ProfileNormalizationResult(
            profile_mappings     = [],
            available_job_titles = [],
            pm_decisions         = {},
        )

    print("[normalization] → récupération des job_title depuis hris.employees…")
    available_job_titles = await _get_job_titles_from_db()
    if not available_job_titles:
        print("[normalization] ⚠️  aucun job_title en base — tous les profils seront none")

    print(
        f"[normalization] → appel LLM : {len(required_profiles)} profils "
        f"× {len(available_job_titles)} job_title disponibles"
    )
    user_prompt  = build_normalization_prompt(required_profiles, available_job_titles)
    raw_response = await _call_llm(user_prompt)

    print("[normalization] → parsing de la réponse LLM…")
    try:
        mappings = _parse_llm_response(raw_response, required_profiles, available_job_titles)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[normalization] ⚠️  parsing échoué ({e}) → fallback none pour tous les profils")
        mappings = [
            ProfileMapping(
                required_profile   = prof,
                matched_job_titles = [],
                match_type         = "none",
                confidence         = 0.0,
                reason             = "Réponse LLM non parseable.",
            )
            for prof in required_profiles
        ]

    # Post-processing : override déterministe exact/none
    mappings = _apply_exact_override(mappings)

    exact_count = sum(1 for m in mappings if m.match_type == "exact")
    close_count = sum(1 for m in mappings if m.match_type == "close")
    none_count  = sum(1 for m in mappings if m.match_type == "none")
    print(
        f"[normalization] ✅ {len(mappings)} profils normalisés — "
        f"exact: {exact_count} | close: {close_count} | none: {none_count}"
    )
    for m in mappings:
        status = "✅" if m.match_type != "none" else "❌"
        print(
            f"[normalization]   {status} '{m.required_profile}' → "
            f"{m.matched_job_titles} ({m.match_type}, {m.confidence:.0%})"
        )

    # Décisions PM par défaut :
    # exact → "accept" (profil trouvé en base, pas de choix à faire)
    # close → "accept" (PM peut changer)
    # none  → "recruit" (aucun match)
    pm_decisions: dict[str, str] = {}
    for m in mappings:
        if m.match_type == "none":
            pm_decisions[m.required_profile] = "recruit"
            print(f"[normalization]   → '{m.required_profile}' pré-marqué 'recruit' (none)")
        else:
            pm_decisions[m.required_profile] = "accept"

    return ProfileNormalizationResult(
        profile_mappings     = mappings,
        available_job_titles = available_job_titles,
        pm_decisions         = pm_decisions,
    )
