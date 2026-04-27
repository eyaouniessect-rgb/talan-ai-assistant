# agents/pm/agents/epics/service.py
# ═══════════════════════════════════════════════════════════════
# Service de génération et d'amélioration des Epics — logique LLM
#
# generate_epics          → 1ère génération depuis le CDC (aucun epic existant)
# improve_targeted_epics  → corrige des epics ciblés (sélection PM)
#                           supporte la scission : db_id=null pour les nouveaux
# improve_all_epics       → applique un feedback global sur la liste complète
#                           sans régénérer depuis zéro (évite les doublons)
# ═══════════════════════════════════════════════════════════════

import asyncio
import json
import re

from agents.pm.agents.epics.prompt import EPICS_SYSTEM_PROMPT, build_epics_prompt
from app.core.groq_client import invoke_with_fallback

_RETRY_DELAYS    = [3, 7]
_VALID_STRATEGIES = {"by_feature", "by_user_role", "by_workflow_step", "by_component"}
_MODEL           = "openai/gpt-oss-120b"


# ──────────────────────────────────────────────────────────────
# Helpers internes
# ──────────────────────────────────────────────────────────────

def _normalize_epics(raw_list: list) -> list[dict]:
    """
    Normalise une liste d'epics bruts retournés par le LLM.
    db_id peut être int, null/None → conservé tel quel.
    Filtre les entrées sans titre.
    """
    result = []
    for e in raw_list:
        if not isinstance(e, dict):
            continue
        strategy = e.get("splitting_strategy", "by_feature")
        if strategy not in _VALID_STRATEGIES:
            strategy = "by_feature"
        title = str(e.get("title", "")).strip()
        if not title:
            continue
        # db_id : int existant ou None (nouvel epic issu d'une scission)
        raw_db_id = e.get("db_id")
        db_id = int(raw_db_id) if raw_db_id is not None and str(raw_db_id).lstrip("-").isdigit() else None
        result.append({
            "db_id":              db_id,
            "title":              title,
            "description":        str(e.get("description", "")),
            "splitting_strategy": strategy,
        })
    return result


async def _call_llm(prompt: str, max_tokens: int = 2048) -> list[dict]:
    """Appelle le LLM, parse le JSON et normalise la liste d'epics."""
    last_error: Exception | None = None
    for attempt in range(1 + len(_RETRY_DELAYS)):
        try:
            raw = await invoke_with_fallback(
                model      = _MODEL,
                messages   = [
                    {"role": "system", "content": EPICS_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens  = max_tokens,
                temperature = 0,
            )
            if not raw or not raw.strip():
                raise ValueError("Reponse vide du LLM")
            clean  = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            data   = json.loads(clean)
            result = _normalize_epics(data.get("epics", []))
            if not result:
                raise ValueError("Aucun epic valide dans la reponse LLM")
            return result

        except Exception as e:
            last_error = e
            if attempt < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt]
                print(f"[epics/llm] Tentative {attempt+1} echouee ({type(e).__name__}: {str(e)[:80]}) -> retry dans {delay}s")
                await asyncio.sleep(delay)

    raise RuntimeError(f"[epics/llm] Echec apres {1+len(_RETRY_DELAYS)} tentatives : {last_error}")


# ──────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────

async def generate_epics(
    cdc_text:       str,
    human_feedback: str | None = None,
) -> tuple[list[dict], list[str]]:
    """
    1ère génération : aucun epic existant → LLM analyse le CDC et crée de zéro.
    Retourne (epics, business_actors).
    """
    user_prompt = build_epics_prompt(cdc_text, human_feedback)
    raw_content = await invoke_with_fallback(
        model    = _MODEL,
        messages = [
            {"role": "system", "content": EPICS_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens  = 4096,
        temperature = 0,
    )
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw_content).strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"[epics] Reponse LLM non-JSON : {e}\nContenu : {raw_content[:300]}")

    epics = data.get("epics", [])
    if not isinstance(epics, list) or not epics:
        raise ValueError(f"[epics] JSON valide mais 'epics' vide ou absent : {data}")

    validated = _normalize_epics(epics)
    if not validated:
        raise ValueError("[epics] Aucun epic valide apres normalisation.")

    # Extraire les acteurs métier (filtre les non-strings et valeurs vides)
    raw_actors = data.get("business_actors", [])
    business_actors = [
        str(a).strip() for a in raw_actors
        if isinstance(a, str) and str(a).strip()
    ]
    print(f"[epics] {len(business_actors)} acteurs metier identifies : {business_actors}")

    epics_clean = [{"title": e["title"], "description": e["description"],
                    "splitting_strategy": e["splitting_strategy"]} for e in validated]
    return epics_clean, business_actors


async def improve_all_epics(
    existing_epics: list[dict],
    cdc_text: str,
    feedback: str,
) -> list[dict]:
    """
    Feedback GLOBAL : applique le feedback sur la liste complète des epics existants.
    Le LLM voit tous les epics (avec db_id) et peut :
      - Modifier un epic existant      → retourne db_id original
      - Scinder un epic en 2           → db_id original pour le 1er, null pour le 2e
      - Ajouter un nouvel epic         → db_id null
      - Renommer / corriger le contenu → db_id original inchangé
    Les epics NON mentionnés dans le feedback sont retournés inchangés.
    """
    epics_text = "\n".join([
        f"  Epic #{i+1} [db_id={e['db_id']}] — {e['title']}"
        for i, e in enumerate(existing_epics)
    ])

    prompt = f"""Le PM a donné ce feedback global sur la liste des epics :

FEEDBACK :
{feedback}

EPICS ACTUELS ({len(existing_epics)}) :
{epics_text}

CONTEXTE CDC (extrait) :
{cdc_text[:2000]}

INSTRUCTIONS :
- Applique le feedback en modifiant uniquement les epics concernés.
- Les epics non concernés par le feedback doivent être retournés INCHANGÉS (même db_id, même contenu).
- Pour RENOMMER un epic : garde le db_id, change seulement le titre.
- Pour SCINDER un epic en 2 : garde le db_id pour la 1ère partie, utilise null pour la nouvelle.
- Pour AJOUTER un epic : utilise db_id null.
- Pour SUPPRIMER un epic : ne l'inclus simplement PAS dans la réponse (ses stories seront aussi supprimées).
- Retourne la liste COMPLÈTE après modifications (les epics supprimés sont absents).

splitting_strategy : "by_feature" | "by_user_role" | "by_workflow_step" | "by_component"

Retourne UNIQUEMENT ce JSON :
{{
  "epics": [
    {{
      "db_id": <id_existant_ou_null>,
      "title": "Titre de l'epic",
      "description": "Description fonctionnelle (2-4 phrases)",
      "splitting_strategy": "by_feature"
    }}
  ]
}}"""

    result = await _call_llm(prompt, max_tokens=3000)
    print(f"[epics/global] {len(result)} epics retournes par le LLM")
    return result


async def improve_targeted_epics(
    epics: list[dict],
    cdc_text: str,
    feedback: str,
) -> list[dict]:
    """
    Feedback CIBLE : corrige uniquement les epics sélectionnés par le PM.
    Supporte la scission : si le feedback demande de couper un epic en 2,
    le LLM peut retourner 2 epics — le 1er garde le db_id original,
    le 2e a db_id=null (sera inséré comme nouvel epic).
    """
    epics_text = "\n\n".join([
        f"Epic #{i+1} [db_id={e['db_id']}]\n"
        f"  Titre       : {e['title']}\n"
        f"  Description : {e.get('description', '')}\n"
        f"  Stratégie   : {e.get('splitting_strategy', 'by_feature')}"
        for i, e in enumerate(epics)
    ])

    prompt = f"""Le PM a ciblé ces epics spécifiques et demande des corrections :

FEEDBACK DU PM :
{feedback}

EPICS À CORRIGER ({len(epics)}) :
{epics_text}

CONTEXTE CDC (extrait) :
{cdc_text[:2000]}

INSTRUCTIONS :
- Applique le feedback sur ces epics uniquement.
- Pour MODIFIER un epic : garde son db_id exact, change le contenu.
- Pour SCINDER en 2 : garde le db_id pour la 1ère partie, mets null pour la 2e.
- Ne retourne QUE les epics qui remplacent ceux fournis (pas les autres epics du projet).

splitting_strategy : "by_feature" | "by_user_role" | "by_workflow_step" | "by_component"

Retourne UNIQUEMENT ce JSON :
{{
  "epics": [
    {{
      "db_id": <id_existant_ou_null_si_scission>,
      "title": "Titre de l'epic",
      "description": "Description fonctionnelle (2-4 phrases)",
      "splitting_strategy": "by_feature"
    }}
  ]
}}"""

    result = await _call_llm(prompt, max_tokens=2048)
    print(f"[epics/targeted] {len(result)} epics retournes (entrée={len(epics)})")
    return result
