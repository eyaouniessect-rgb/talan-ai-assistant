# agents/pm/agents/stories/tools/estimate.py
# ═══════════════════════════════════════════════════════════════
# Logique LLM — Estimation des Story Points (Fibonacci)
#
# Utilisé par les @tool wrappers dans react_agent.py
# ═══════════════════════════════════════════════════════════════

import json
import re

from app.core.groq_client import invoke_with_fallback

_MODEL     = "openai/gpt-oss-120b"
_FIBONACCI = {1, 2, 3, 5, 8}  # 13 volontairement exclu

_SYSTEM = """Tu es un expert en estimation Agile (Planning Poker).
Tu estimes les story points en suivant la suite de Fibonacci : 1, 2, 3, 5, 8.
13 est INTERDIT — si une story semble valoir 13, mets 8 (elle devra être découpée plus tard).
Règles : 1-2pts=simple, 3-5pts=complexité normale, 8pts=fonctionnalité complexe.
Réponds UNIQUEMENT avec du JSON valide, sans markdown."""


async def run_estimate_story_points(stories: list[dict]) -> list[dict]:
    """
    Estime les story points pour une liste de stories.
    Retourne la même liste avec 'story_points' renseigné (Fibonacci 1-8).
    """
    if not stories:
        return stories

    stories_text = "\n".join([
        f"{i}. {s['title']}\n   {s.get('description', '')[:150]}"
        for i, s in enumerate(stories)
    ])

    prompt = f"""Estime les story points (1, 2, 3, 5 ou 8) pour chaque story.
13 est INTERDIT — si une story mérite 13, mets 8.

Stories :
{stories_text}

Retourne UNIQUEMENT ce JSON :
{{
  "estimates": [
    {{"index": 0, "story_points": 3, "reason": "une phrase courte"}}
  ]
}}"""

    raw = await invoke_with_fallback(
        model      = _MODEL,
        messages   = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        max_tokens  = 600,
        temperature = 0,
    )

    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    try:
        data = json.loads(clean)
        estimates = {int(e["index"]): e["story_points"] for e in data.get("estimates", [])}
    except (json.JSONDecodeError, KeyError, TypeError):
        print("[estimate] ⚠ JSON invalide → fallback 3 pts")
        return [{**s, "story_points": 3} for s in stories]

    result = []
    for i, s in enumerate(stories):
        sp = estimates.get(i, 3)
        if sp not in _FIBONACCI:
            sp = min(_FIBONACCI, key=lambda x: abs(x - sp))
        result.append({**s, "story_points": sp})

    return result
