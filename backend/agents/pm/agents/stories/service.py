# agents/pm/agents/stories/service.py
# Phase 3 — Logique LLM pour la génération des User Stories

import json
import re

from agents.pm.agents.stories.prompt import STORIES_SYSTEM_PROMPT, build_stories_prompt
from app.core.groq_client import invoke_with_fallback

_FIBONACCI = {1, 2, 3, 5, 8, 13, 21}
_MODEL     = "openai/gpt-oss-120b"


async def generate_stories(
    epics:          list[dict],
    human_feedback: str | None = None,
) -> list[dict]:
    """
    Génère les user stories depuis les epics via LLM.
    Retourne une liste de stories validées.
    """
    user_prompt = build_stories_prompt(epics, human_feedback)

    raw = await invoke_with_fallback(
        model    = _MODEL,
        messages = [
            {"role": "system", "content": STORIES_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens  = 4096,
        temperature = 0,
    )
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"[stories] JSON invalide : {e}\n{raw[:300]}")

    stories = data.get("stories", [])
    if not stories:
        raise ValueError(f"[stories] Aucune story dans la réponse : {data}")

    validated = []
    for i, s in enumerate(stories):
        if not isinstance(s, dict):
            continue
        sp = s.get("story_points", 3)
        if sp not in _FIBONACCI:
            sp = min(_FIBONACCI, key=lambda x: abs(x - sp))
        validated.append({
            "epic_id":             int(s.get("epic_id", 0)),
            "title":               str(s.get("title", f"Story {i+1}")),
            "description":         str(s.get("description", "")),
            "story_points":        sp,
            "acceptance_criteria": list(s.get("acceptance_criteria", [])),
            "splitting_strategy":  str(s.get("splitting_strategy", "by_feature")),
        })

    return validated
