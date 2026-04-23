# agents/pm/agents/stories/tools/review.py
# ═══════════════════════════════════════════════════════════════
# Logique LLM — Revue de couverture fonctionnelle
#
# Utilisé par les @tool wrappers dans react_agent.py
# ═══════════════════════════════════════════════════════════════

import asyncio
import json
import re

from app.core.groq_client import invoke_with_fallback

_RETRY_DELAYS = [3, 7]   # secondes avant 1er et 2e retry

_MODEL = "openai/gpt-oss-120b"

_SYSTEM = """Tu es un expert Agile (Product Owner senior) qui audite la qualité des User Stories.
Tu vérifies 3 dimensions :
  1. COMPLÉTUDE    : les stories couvrent-elles les fonctionnalités majeures de l'epic ?
  2. SCOPE CREEP   : aucune story ne doit aller au-delà du périmètre de l'epic.
  3. QUALITÉ INVEST: chaque story doit être Indépendante, Négociable, Valeur, Estimable, Small, Testable.
Réponds UNIQUEMENT avec du JSON valide, sans markdown."""


async def run_review_coverage(epic: dict, epic_idx: int, stories: list[dict]) -> dict:
    """
    Vérifie la couverture, le scope creep et la qualité des stories par rapport à l'epic.
    Retourne { coverage_ok, gaps, scope_creep_issues, quality_issues, suggestions }.
    En cas d'erreur LLM : retourne coverage_ok=True (fail-safe).
    """
    stories_text = "\n".join([
        f"  {i}. {s['title']} ({s.get('story_points', '?')} pts)"
        for i, s in enumerate(stories)
    ])

    prompt = f"""Audite ces User Stories par rapport à l'epic.

EPIC #{epic_idx} :
  Titre       : {epic['title']}
  Description : {epic.get('description', '')}
  Stratégie   : {epic.get('splitting_strategy', 'by_feature')}

STORIES GÉNÉRÉES ({len(stories)}) :
{stories_text}

══════════════════════════════════════
VÉRIFIE CES 3 POINTS :
══════════════════════════════════════
1. GAPS (complétude) : fonctionnalités majeures de l'epic non couvertes par les stories
2. SCOPE CREEP : stories qui sortent du périmètre de l'epic (trop larges, touchent un autre epic)
3. QUALITÉ : stories mal formulées, trop grandes (> 8 pts justifié), ou non testables

Règles :
- Sois strict sur le scope creep : une story doit rester dans les limites de cet epic
- Ignore les détails techniques mineurs comme gaps
- Si tout est satisfaisant → coverage_ok=true et listes vides

Retourne UNIQUEMENT ce JSON :
{{
  "coverage_ok": true,
  "gaps": [],
  "scope_creep_issues": [],
  "quality_issues": [],
  "suggestions": []
}}"""

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
                max_tokens  = 768,
                temperature = 0,
            )

            if not raw or not raw.strip():
                raise ValueError("Réponse vide du LLM (No message content)")

            clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            data  = json.loads(clean)

            scope_issues   = list(data.get("scope_creep_issues", []))
            quality_issues = list(data.get("quality_issues", []))
            gaps           = list(data.get("gaps", []))

            if scope_issues:
                print(f"[review]   ⚠ Scope creep détecté pour epic {epic_idx} : {scope_issues}")
            if quality_issues:
                print(f"[review]   ⚠ Problèmes qualité pour epic {epic_idx} : {quality_issues}")

            if attempt > 0:
                print(f"[review]   Epic {epic_idx} OK après {attempt} retry")

            return {
                "coverage_ok":        bool(data.get("coverage_ok", True)),
                "gaps":               gaps,
                "scope_creep_issues": scope_issues,
                "quality_issues":     quality_issues,
                "suggestions":        list(data.get("suggestions", [])),
            }

        except Exception as e:
            last_error = e
            if attempt < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt]
                print(f"[review] ⚠ Epic {epic_idx} tentative {attempt + 1} échouée ({type(e).__name__}: {str(e)[:80]}) → retry dans {delay}s")
                await asyncio.sleep(delay)

    print(f"[review] ✗ Epic {epic_idx} — {attempts} tentatives échouées → coverage_ok=True fail-safe")
    return {"coverage_ok": True, "gaps": [], "scope_creep_issues": [], "quality_issues": [], "suggestions": []}
