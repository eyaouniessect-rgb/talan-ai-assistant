# agents/pm/agents/stories/tools/generate.py
# ═══════════════════════════════════════════════════════════════
# Logique LLM — Génération complète des User Stories pour UN seul epic
#
# 1 seul appel LLM par epic : title + description + story_points + acceptance_criteria
# (remplace les 3 appels séparés : generate + estimate + criteria)
# ═══════════════════════════════════════════════════════════════

import asyncio
import json
import re

from app.core.groq_client import invoke_with_fallback

_RETRY_DELAYS = [3, 7]   # secondes avant 1er et 2e retry

_MODEL     = "openai/gpt-oss-120b"
_FIBONACCI = {1, 2, 3, 5, 8}

_SYSTEM = """Tu es un expert Agile (Product Owner senior + QA).
Tu décomposes un epic en User Stories complètes : titre, description, story points et critères d'acceptation.

Règles STORY :
- Format titre : "En tant que [rôle précis], je veux [action concrète] afin de [bénéfice métier]"
- Coupe verticale obligatoire (UI + backend + DB si applicable)
- Indépendance INVEST : chaque story livrable seule
- 2 à 8 stories selon la complexité de l'epic

Règles STORY POINTS (suite Fibonacci uniquement) :
- 1 = trivial (affichage simple, lecture seule)
- 2 = simple (un seul composant, pas d'état)
- 3 = complexité normale (formulaire + validation + API)
- 5 = complexe (plusieurs composants, logique métier)
- 8 = très complexe (intégration externe, workflow multi-étapes)
- 13 est INTERDIT — si une story mérite 13, mets 8 (elle sera découpée)

Règles CRITÈRES D'ACCEPTATION (Gherkin) :
- Format : "Étant donné [contexte], quand [action], alors [résultat mesurable]"
- 2 à 3 critères par story (jamais plus de 3)
- Obligatoire : au moins 1 critère nominal ET 1 critère négatif (erreur, donnée invalide)

Réponds UNIQUEMENT avec du JSON valide, sans markdown, sans texte avant ou après."""


def _build_prompt(
    epic: dict,
    epic_idx: int,
    architecture_details: dict | None,
    missing_features: list[str] | None,
    human_feedback: str | None,
) -> str:
    strategy = epic.get("splitting_strategy", "by_feature")

    feedback_section = (
        f"\n⚠ CORRECTIONS DU PM — intègre ces retours :\n{human_feedback}\n"
    ) if human_feedback else ""

    missing_section = ""
    if missing_features:
        items = "\n".join(f"  - {f}" for f in missing_features)
        missing_section = (
            f"\n⚠ FONCTIONNALITÉS MANQUANTES À COUVRIR OBLIGATOIREMENT :\n"
            f"{items}\n"
            f"(En plus des stories normales, crée des stories couvrant ces points)\n"
        )

    arch_section = ""
    if architecture_details:
        layers = architecture_details.get("layers", [])
        agents = architecture_details.get("agents", [])
        if layers or agents:
            lines = ["\nARCHITECTURE CIBLE — nommer les composants dans les descriptions :"]
            for layer in layers:
                comps = ", ".join(layer.get("components", []))
                if comps:
                    lines.append(f"  • {layer.get('name', '')}: {comps}")
            for a in agents:
                aname = a.get("name", "")
                arole = a.get("role", "")
                role_str = f" ({arole})" if arole and arole != aname else ""
                lines.append(f"  • Agent: {aname}{role_str}")
            arch_section = "\n".join(lines) + "\n"

    return f"""Décompose cet epic en User Stories Agile COMPLÈTES (titre + description + story_points + acceptance_criteria).
{feedback_section}{missing_section}
══════════════════════════════════════════════════════════════
EPIC #{epic_idx} (stratégie : {strategy})
══════════════════════════════════════════════════════════════
Titre       : {epic['title']}
Description : {epic.get('description', '')}
{arch_section}
══════════════════════════════════════════════════════════════
FORMAT JSON ATTENDU (sans markdown)
══════════════════════════════════════════════════════════════
{{
  "stories": [
    {{
      "title": "En tant que [rôle précis], je veux [action concrète] afin de [bénéfice métier]",
      "description": "Contexte fonctionnel détaillé (composants impliqués, flux attendu).",
      "story_points": 3,
      "acceptance_criteria": [
        "Étant donné [contexte nominal], quand [action principale], alors [résultat attendu]",
        "Étant donné [donnée invalide], quand [action invalide], alors [message d'erreur explicite]"
      ],
      "splitting_strategy": "{strategy}"
    }}
  ]
}}"""


async def run_generate_for_epic(
    epic: dict,
    epic_idx: int,
    architecture_details: dict | None = None,
    missing_features: list[str] | None = None,
    human_feedback: str | None = None,
) -> list[dict]:
    """
    Génère les User Stories complètes (titre + description + SP + AC) pour un seul epic.
    1 seul appel LLM — remplace les anciens appels séparés generate + estimate + criteria.
    """
    prompt = _build_prompt(epic, epic_idx, architecture_details, missing_features, human_feedback)

    last_error: Exception | None = None
    attempts = 1 + len(_RETRY_DELAYS)
    data: dict = {}

    for attempt in range(attempts):
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
                raise ValueError("Réponse vide du LLM (No message content)")

            clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            data  = json.loads(clean)

            if attempt > 0:
                print(f"[generate]   Epic {epic_idx} OK après {attempt} retry")
            break

        except Exception as e:
            last_error = e
            if attempt < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt]
                print(f"[generate] ⚠ Epic {epic_idx} tentative {attempt + 1} échouée ({type(e).__name__}: {str(e)[:80]}) → retry dans {delay}s")
                await asyncio.sleep(delay)
            else:
                print(f"[generate] ✗ Epic {epic_idx} — {attempts} tentatives échouées → fallback story")
                return [_fallback_story(epic, epic_idx)]

    raw_stories = data.get("stories", [])
    if not raw_stories:
        print(f"[generate] ⚠ Aucune story pour epic {epic_idx}")
        return [_fallback_story(epic, epic_idx)]

    result = []
    for i, s in enumerate(raw_stories):
        if not isinstance(s, dict):
            continue

        sp = s.get("story_points", 3)
        if not isinstance(sp, int) or sp not in _FIBONACCI:
            sp = min(_FIBONACCI, key=lambda x: abs(x - (sp if isinstance(sp, (int, float)) else 3)))

        ac = s.get("acceptance_criteria", [])
        if not isinstance(ac, list) or not ac:
            ac = ["À définir"]

        result.append({
            "epic_id":             epic_idx,
            "title":               str(s.get("title", f"Story {i + 1}")),
            "description":         str(s.get("description", "")),
            "story_points":        sp,
            "acceptance_criteria": ac,
            "splitting_strategy":  str(s.get("splitting_strategy",
                                              epic.get("splitting_strategy", "by_feature"))),
        })

    print(f"[generate]   Epic {epic_idx} → {len(result)} stories (SP + AC inclus)")
    return result


def _fallback_story(epic: dict, epic_idx: int) -> dict:
    return {
        "epic_id":             epic_idx,
        "title":               f"Story à définir pour : {epic.get('title', 'Epic ' + str(epic_idx))}",
        "description":         epic.get("description", "Description à compléter manuellement."),
        "story_points":        3,
        "acceptance_criteria": ["À définir"],
        "splitting_strategy":  epic.get("splitting_strategy", "by_feature"),
    }
