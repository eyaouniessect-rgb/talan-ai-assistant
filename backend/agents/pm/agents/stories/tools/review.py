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


def _to_str_list(lst: list) -> list[str]:
    """Normalise une liste LLM en liste de strings (le LLM peut retourner des dicts)."""
    result = []
    for item in lst:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # Essaie les clés courantes avant de fallback sur str()
            text = (
                item.get("description") or item.get("gap") or item.get("issue")
                or item.get("text") or item.get("message") or str(item)
            )
            result.append(str(text))
        else:
            result.append(str(item))
    return result

_MODEL = "openai/gpt-oss-120b"

_SYSTEM = """Tu es un expert Agile (Product Owner senior) qui audite la qualité des User Stories.
Tu vérifies 4 dimensions :
  1. COMPLÉTUDE    : les stories couvrent-elles les fonctionnalités majeures de l'epic ?
  2. SCOPE CREEP   : aucune story ne doit aller au-delà du périmètre de l'epic.
  3. QUALITÉ INVEST: les critères INVEST s'appliquent selon la stratégie de découpage (voir règles ci-dessous).
  4. PERSPECTIVE ACTEUR : chaque story doit être rédigée du point de vue d'un acteur HUMAIN du domaine métier.
     Les acteurs INTERDITS sont : "système", "application", "API", "backend", "frontend", "base de données",
     "serveur", "module", "algorithme", "composant", "admin technique".
     Une story avec un acteur interdit est un gap de qualité CRITIQUE à signaler dans quality_issues.

INVEST ADAPTÉ PAR STRATÉGIE DE DÉCOUPAGE :
  by_feature       → INVEST complet (Indépendante, Négociable, Valuable, Estimable, Small, Testable)
  by_user_role     → INVEST complet + "Valuable" prioritaire : chaque story doit apporter
                     une valeur métier explicite au rôle ciblé
  by_workflow_step → Indépendance IGNORÉE : le couplage séquentiel est inhérent à cette
                     stratégie (l'étape 2 dépend de l'étape 1 par conception).
                     Priorité sur Small et Testable.
  by_component     → "Valuable" ASSOUPLI : un composant technique n'est pas toujours
                     directement valorisable pour l'utilisateur final.
                     Priorité sur Testable (couverture unitaire attendue).

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

    strategy = epic.get("splitting_strategy", "by_feature")

    # Message contextuel selon la stratégie — rappel de l'exception INVEST
    _STRATEGY_HINTS = {
        "by_feature": (
            "Stratégie : by_feature — INVEST complet. "
            "Vérifie tous les critères sans exception."
        ),
        "by_user_role": (
            "Stratégie : by_user_role — INVEST complet. "
            "Insiste sur 'Valuable' : chaque story doit mentionner explicitement "
            "la valeur apportée au rôle ciblé."
        ),
        "by_workflow_step": (
            "Stratégie : by_workflow_step — NE PÉNALISE PAS les dépendances séquentielles "
            "entre stories (ex : 'l'étape 2 dépend de l'étape 1'). "
            "Ce couplage est voulu. Concentre l'audit sur Small et Testable."
        ),
        "by_component": (
            "Stratégie : by_component — ASSOUPLIS le critère 'Valuable' pour les stories "
            "purement techniques (un composant infrastructure n'a pas toujours de valeur "
            "utilisateur directe). Concentre l'audit sur Testable."
        ),
    }
    strategy_hint = _STRATEGY_HINTS.get(strategy, _STRATEGY_HINTS["by_feature"])

    prompt = f"""Audite ces User Stories par rapport à l'epic.

EPIC #{epic_idx} :
  Titre       : {epic['title']}
  Description : {epic.get('description', '')}
  Stratégie   : {strategy}

{strategy_hint}

STORIES GÉNÉRÉES ({len(stories)}) :
{stories_text}

══════════════════════════════════════
VÉRIFIE CES 4 POINTS :
══════════════════════════════════════
1. GAPS (complétude) : fonctionnalités majeures de l'epic non couvertes par les stories
2. SCOPE CREEP : stories qui sortent du périmètre de l'epic (trop larges, touchent un autre epic)
3. QUALITÉ INVEST : applique les critères INVEST adaptés à la stratégie indiquée ci-dessus
4. PERSPECTIVE ACTEUR : signale dans quality_issues chaque story dont l'acteur n'est pas un rôle humain métier
   (ex: "En tant que système…", "En tant qu'application…" → quality_issue critique)

Règles générales :
- Sois strict sur le scope creep : une story doit rester dans les limites de cet epic
- Ignore les détails techniques mineurs comme gaps
- Respecte l'adaptation INVEST selon la stratégie (ne pénalise pas ce qui est normal pour la stratégie)
- Une story avec un acteur interdit (système, application, API…) est TOUJOURS un quality_issue
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
                model          = _MODEL,
                messages       = [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens     = 768,
                temperature    = 0,
                nvidia_retries = 2,   # 2 tentatives par clé (temp 0 puis 0.05)
            )

            if not raw or not raw.strip():
                raise ValueError("Réponse vide du LLM (No message content)")

            clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            data  = json.loads(clean)

            scope_issues   = _to_str_list(data.get("scope_creep_issues", []))
            quality_issues = _to_str_list(data.get("quality_issues", []))
            gaps           = _to_str_list(data.get("gaps", []))

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
