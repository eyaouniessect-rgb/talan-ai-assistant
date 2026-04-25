# agents/pm/agents/stories/tools/targeted_regen.py
# ═══════════════════════════════════════════════════════════════
# Régénération ciblée — améliore des stories spécifiques
# selon le feedback du PM, sans toucher aux autres.
# ═══════════════════════════════════════════════════════════════

import asyncio
import json
import re

from app.core.groq_client import invoke_with_fallback

_MODEL        = "openai/gpt-oss-120b"
_RETRY_DELAYS = [3, 7]
_FIBONACCI    = {1, 2, 3, 5, 8}

_SYSTEM = """Tu es un expert Agile (Product Owner senior + QA) qui améliore des User Stories existantes.
Tu appliques fidèlement le feedback du PM : détails manquants, reformulation, critères d'acceptation, story points.
Garde toujours le db_id exact de chaque story — ne le modifie jamais.
Format titre : "En tant que [rôle précis], je veux [action concrète] afin de [bénéfice métier]"
Critères d'acceptation Gherkin : "Étant donné [contexte], quand [action], alors [résultat mesurable]"
Réponds UNIQUEMENT avec du JSON valide, sans markdown."""


async def improve_targeted_stories(
    stories: list[dict],
    feedback: str,
) -> list[dict]:
    """
    Améliore les stories ciblées par le PM en tenant compte du feedback.
    Chaque story doit avoir : db_id, title, description, story_points,
                              acceptance_criteria, epic_title.
    Retourne les mêmes stories avec contenu amélioré (db_id inchangé).
    En cas d'échec total : retourne les stories originales (fail-safe).
    """
    stories_text = "\n\n".join([
        f"Story #{i+1} [db_id={s['db_id']}] — epic: {s.get('epic_title', '?')}\n"
        f"  Titre       : {s['title']}\n"
        f"  Description : {s.get('description', '')}\n"
        f"  SP          : {s.get('story_points', '?')}\n"
        f"  Critères    : {json.dumps(s.get('acceptance_criteria', []), ensure_ascii=False)}"
        for i, s in enumerate(stories)
    ])

    prompt = f"""FEEDBACK DU PM :
{feedback}

STORIES À CORRIGER ({len(stories)}) :
{stories_text}

Corrige TOUTES ces stories en appliquant le feedback du PM.
RÈGLE ABSOLUE : le champ "db_id" de chaque story doit rester IDENTIQUE à celui fourni.

Retourne UNIQUEMENT ce JSON :
{{
  "stories": [
    {{
      "db_id": <db_id_exact>,
      "title": "En tant que [rôle], je veux [action] afin de [bénéfice]",
      "description": "Description améliorée et détaillée",
      "story_points": 3,
      "acceptance_criteria": [
        "Étant donné [contexte nominal], quand [action], alors [résultat]",
        "Étant donné [données invalides], quand [action invalide], alors [message d'erreur]"
      ]
    }}
  ]
}}"""

    last_error: Exception | None = None
    for attempt in range(1 + len(_RETRY_DELAYS)):
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

            result = []
            for s in data.get("stories", []):
                if not isinstance(s, dict) or "db_id" not in s:
                    continue
                sp = s.get("story_points", 3)
                if not isinstance(sp, int) or sp not in _FIBONACCI:
                    sp = min(_FIBONACCI, key=lambda x: abs(x - (sp if isinstance(sp, (int, float)) else 3)))
                ac = s.get("acceptance_criteria", [])
                if not isinstance(ac, list) or not ac:
                    ac = ["À définir"]
                result.append({
                    "db_id":               int(s["db_id"]),
                    "title":               str(s.get("title", "")),
                    "description":         str(s.get("description", "")),
                    "story_points":        sp,
                    "acceptance_criteria": ac,
                })

            if not result:
                raise ValueError("Aucune story valide dans la réponse LLM")

            print(f"[targeted_regen] {len(result)} stories améliorées")
            return result

        except Exception as e:
            last_error = e
            if attempt < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt]
                print(f"[targeted_regen] Tentative {attempt+1} échouée ({type(e).__name__}: {str(e)[:80]}) → retry dans {delay}s")
                await asyncio.sleep(delay)

    print(f"[targeted_regen] Échec — retour stories originales (fail-safe). Erreur: {last_error}")
    return stories  # fail-safe : retourner les originales inchangées
