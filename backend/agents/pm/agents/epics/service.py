# agents/pm/agents/epics/service.py
# ═══════════════════════════════════════════════════════════════
# Service de génération des Epics — logique LLM
#
# Responsabilités :
#   - Appeler le LLM (Groq llama-3.3-70b-versatile)
#   - Parser la réponse JSON
#   - Valider la structure des epics retournés
# ═══════════════════════════════════════════════════════════════

import json
import re

from agents.pm.agents.epics.prompt import EPICS_SYSTEM_PROMPT, build_epics_prompt
from app.core.groq_client import invoke_with_fallback

# Valeurs autorisées pour splitting_strategy
_VALID_STRATEGIES = {"by_feature", "by_user_role", "by_workflow_step", "by_component"}

# Modèle LLM utilisé pour la génération des epics
_MODEL = "openai/gpt-oss-120b"


async def generate_epics(
    cdc_text:       str,
    human_feedback: str | None = None,
) -> list[dict]:
    """
    Appelle le LLM pour générer les epics depuis le CDC.

    Paramètres :
      cdc_text       — texte brut du CDC extrait en phase 1
      human_feedback — feedback PM si la phase a été rejetée (None sinon)

    Retourne une liste d'epics validés.
    Lève ValueError si le JSON est invalide ou la structure incorrecte.
    """
    user_prompt = build_epics_prompt(cdc_text, human_feedback)

    # ── Appel LLM avec fallback NVIDIA → Groq ────────────────
    raw_content = await invoke_with_fallback(
        model    = _MODEL,
        messages = [
            {"role": "system", "content": EPICS_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens  = 4096,
        temperature = 0,
    )

    # ── Parsing JSON ──────────────────────────────────────────
    # Nettoyer les éventuels blocs markdown ```json ... ```
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw_content).strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"[epics] Réponse LLM non-JSON : {e}\nContenu : {raw_content[:300]}")

    epics = data.get("epics", [])
    if not isinstance(epics, list) or len(epics) == 0:
        raise ValueError(f"[epics] JSON valide mais 'epics' vide ou absent : {data}")

    # ── Validation et normalisation ───────────────────────────
    validated = []
    for i, epic in enumerate(epics):
        if not isinstance(epic, dict):
            continue
        strategy = epic.get("splitting_strategy", "by_feature")
        if strategy not in _VALID_STRATEGIES:
            strategy = "by_feature"
        validated.append({
            "title":              str(epic.get("title", f"Epic {i+1}")),
            "description":        str(epic.get("description", "")),
            "splitting_strategy": strategy,
        })

    if not validated:
        raise ValueError("[epics] Aucun epic valide après normalisation.")

    return validated
