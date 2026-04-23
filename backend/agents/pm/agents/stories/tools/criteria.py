# agents/pm/agents/stories/tools/criteria.py
# ═══════════════════════════════════════════════════════════════
# Logique LLM — Génération des critères d'acceptation (Gherkin)
# ═══════════════════════════════════════════════════════════════

import json
import re

from app.core.groq_client import invoke_with_fallback

_MODEL      = "openai/gpt-oss-120b"
_BATCH_SIZE = 15  # modèle 128k — toutes les stories d'un epic tiennent en 1 appel

_SYSTEM = """Tu es un expert en qualité logicielle (QA / BDD).
Tu génères des critères d'acceptation au format Gherkin.
Format OBLIGATOIRE : "Étant donné [contexte], quand [action], alors [résultat mesurable]"
Maximum 3 critères par story. Ne jamais dépasser 3.
Réponds UNIQUEMENT avec du JSON valide, sans markdown, sans texte avant ou après."""


def _build_batch_prompt(batch: list[tuple[int, dict]]) -> str:
    stories_text = "\n".join([
        f"{orig_idx}. {s['title']}\n   {s.get('description', '')[:120]}"
        for orig_idx, s in batch
    ])
    indices = [str(orig_idx) for orig_idx, _ in batch]

    return f"""Génère les critères d'acceptation Gherkin pour chaque story.
Règles :
- Maximum 3 critères par story (jamais plus)
- Au moins 1 critère négatif (cas d'erreur ou donnée invalide)
- Format : "Étant donné [contexte], quand [action], alors [résultat mesurable]"

Stories :
{stories_text}

Retourne UNIQUEMENT ce JSON (indices : {', '.join(indices)}) :
{{
  "criteria": [
    {{
      "index": {indices[0]},
      "acceptance_criteria": [
        "Étant donné [contexte nominal], quand [action principale], alors [résultat attendu]",
        "Étant donné [donnée invalide], quand [action invalide], alors [message d'erreur explicite]"
      ]
    }}
  ]
}}"""


async def _generate_batch_criteria(batch: list[tuple[int, dict]]) -> dict[int, list[str]]:
    prompt = _build_batch_prompt(batch)

    raw = await invoke_with_fallback(
        model      = _MODEL,
        messages   = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        max_tokens  = 4096,
        temperature = 0,
    )

    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    try:
        data = json.loads(clean)
        return {
            int(c["index"]): list(c["acceptance_criteria"])
            for c in data.get("criteria", [])
            if isinstance(c, dict) and "index" in c and "acceptance_criteria" in c
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        print(f"[criteria] ⚠ Batch JSON invalide : {e} → fallback 'À définir' pour ce batch")
        return {}


async def run_generate_acceptance_criteria(stories: list[dict]) -> list[dict]:
    """
    Génère les critères d'acceptation Gherkin pour une liste de stories.
    Traitement par batch de {_BATCH_SIZE} stories (1 appel LLM pour la plupart des epics).
    """
    if not stories:
        return stories

    batches: list[list[tuple[int, dict]]] = []
    for start in range(0, len(stories), _BATCH_SIZE):
        batch = [(i, stories[i]) for i in range(start, min(start + _BATCH_SIZE, len(stories)))]
        batches.append(batch)

    print(f"[criteria] {len(stories)} stories → {len(batches)} appel(s) LLM")

    all_criteria: dict[int, list[str]] = {}
    for batch_idx, batch in enumerate(batches):
        print(f"[criteria]   Appel {batch_idx + 1}/{len(batches)} ({len(batch)} stories)")
        batch_result = await _generate_batch_criteria(batch)
        all_criteria.update(batch_result)

    result = []
    for i, s in enumerate(stories):
        ac = all_criteria.get(i) or ["À définir"]
        result.append({**s, "acceptance_criteria": ac})

    total_ac = sum(len(r["acceptance_criteria"]) for r in result)
    print(f"[criteria] ✓ {total_ac} critères générés pour {len(result)} stories")
    return result
