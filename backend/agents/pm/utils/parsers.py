# agents/pm/utils/parsers.py
# ═══════════════════════════════════════════════════════════════
# Utilitaires de parsing partagés par tous les agents PM.
# ═══════════════════════════════════════════════════════════════

import json
import re


def parse_llm_json(raw_content: str) -> dict:
    """
    Parse le contenu JSON d'une réponse LLM.
    Nettoie les éventuels blocs markdown ```json ... ```.
    Lève ValueError si le JSON est invalide.
    """
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw_content).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"Réponse LLM non-JSON : {e}\nContenu : {raw_content[:300]}")


def normalize_fibonacci(value: int) -> int:
    """
    Arrondit une valeur au plus proche nombre de Fibonacci (1,2,3,5,8,13,21).
    Utilisé pour normaliser les story_points.
    """
    fibonacci = [1, 2, 3, 5, 8, 13, 21]
    return min(fibonacci, key=lambda x: abs(x - value))
