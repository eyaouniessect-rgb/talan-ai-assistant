# agents/pm/agents/stories/tools/criteria.py
# ═══════════════════════════════════════════════════════════════
# Logique LLM — Génération des critères d'acceptation (Gherkin)
#
# Problème résolu : les réponses LLM pour beaucoup de stories
# dépassaient max_tokens → JSON tronqué → JSONDecodeError.
#
# Solution : traitement par batch de 3 stories maximum.
# Chaque appel LLM génère les AC d'au plus 3 stories → réponse
# courte (~600 tokens) impossible à tronquer.
# ═══════════════════════════════════════════════════════════════

import json
import re

from app.core.groq_client import invoke_with_fallback

_MODEL      = "openai/gpt-oss-120b"
_BATCH_SIZE = 2   # max stories par appel LLM (réduit pour éviter la troncature JSON)

_SYSTEM = """Tu es un expert en qualité logicielle (QA / BDD).
Tu génères des critères d'acceptation au format Gherkin.
Format OBLIGATOIRE : "Étant donné [contexte], quand [action], alors [résultat mesurable]"
MAXIMUM 3 critères par story : 2 critères positifs + 1 critère négatif (cas d'erreur).
Réponds UNIQUEMENT avec du JSON valide, sans markdown, sans texte avant ou après."""


def _build_batch_prompt(batch: list[tuple[int, dict]]) -> str:
    """Construit le prompt pour un batch de (index_global, story)."""
    stories_text = "\n".join([
        f"{orig_idx}. {s['title']}\n   {s.get('description', '')[:120]}"
        for orig_idx, s in batch
    ])
    indices = [str(orig_idx) for orig_idx, _ in batch]

    return f"""Génère EXACTEMENT 3 critères d'acceptation Gherkin par story (2 positifs + 1 négatif).
MAXIMUM 3 critères — ne jamais en mettre plus.

Stories :
{stories_text}

Retourne UNIQUEMENT ce JSON (indices : {', '.join(indices)}) :
{{
  "criteria": [
    {{
      "index": {indices[0]},
      "acceptance_criteria": [
        "Étant donné [contexte nominal], quand [action principale], alors [résultat attendu]",
        "Étant donné [contexte alternatif], quand [action secondaire], alors [résultat attendu]",
        "Étant donné [donnée invalide], quand [action invalide], alors [message d'erreur explicite]"
      ]
    }}
  ]
}}"""


async def _generate_batch_criteria(batch: list[tuple[int, dict]]) -> dict[int, list[str]]:
    """
    Appelle le LLM pour un batch de stories.
    Retourne un dict { index_global → [critères] }.
    """
    prompt = _build_batch_prompt(batch)

    raw = await invoke_with_fallback(
        model      = _MODEL,
        messages   = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        max_tokens  = 2048,   # 2 stories × 4 critères Gherkin verbeux ≈ 800 tokens réels
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
        return {}   # fallback géré dans run_generate_acceptance_criteria


async def run_generate_acceptance_criteria(stories: list[dict]) -> list[dict]:
    """
    Génère les critères d'acceptation Gherkin pour une liste de stories.
    Traitement par batch de {_BATCH_SIZE} stories pour éviter la troncature.

    Retourne la même liste avec 'acceptance_criteria' renseigné.
    Fallback = ["À définir"] si le LLM échoue sur un batch.
    """
    if not stories:
        return stories

    # Construire les batches avec l'index global pour chaque story
    batches: list[list[tuple[int, dict]]] = []
    for start in range(0, len(stories), _BATCH_SIZE):
        batch = [(i, stories[i]) for i in range(start, min(start + _BATCH_SIZE, len(stories)))]
        batches.append(batch)

    print(f"[criteria] {len(stories)} stories → {len(batches)} batch(es) de {_BATCH_SIZE}")

    # Collecter tous les résultats
    all_criteria: dict[int, list[str]] = {}
    for batch_idx, batch in enumerate(batches):
        print(f"[criteria]   Batch {batch_idx + 1}/{len(batches)} ({len(batch)} stories)")
        batch_result = await _generate_batch_criteria(batch)
        all_criteria.update(batch_result)

    # Appliquer les critères à chaque story
    result = []
    for i, s in enumerate(stories):
        ac = all_criteria.get(i)
        if not ac:
            ac = ["À définir"]   # fallback si le batch a échoué
        result.append({**s, "acceptance_criteria": ac})

    total_ac = sum(len(r["acceptance_criteria"]) for r in result)
    print(f"[criteria] ✓ {total_ac} critères générés pour {len(result)} stories")
    return result
