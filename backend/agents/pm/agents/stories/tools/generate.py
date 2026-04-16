# agents/pm/agents/stories/tools/generate.py
# ═══════════════════════════════════════════════════════════════
# Logique LLM — Génération des User Stories pour UN seul epic
#
# Utilisé par les @tool wrappers dans react_agent.py
# Traitement ciblé (1 epic à la fois) → résout la troncature
# ═══════════════════════════════════════════════════════════════

import json
import re

from app.core.groq_client import invoke_with_fallback

_MODEL = "openai/gpt-oss-120b"

_SYSTEM = """Tu es un expert Agile (Product Owner senior).
Tu décomposes un epic en User Stories au bon niveau de granularité.
Chaque story doit suivre le format "En tant que [rôle précis], je veux [action concrète] afin de [bénéfice métier]".
Les stories doivent être indépendantes (INVEST), verticales (UI + backend si applicable).
Réponds UNIQUEMENT avec du JSON valide, sans markdown."""


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
            f"(En plus des stories normales, assure-toi de créer des stories qui couvrent ces points)\n"
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

    return f"""Décompose cet epic en User Stories Agile.
{feedback_section}{missing_section}
══════════════════════════════════════════════════════════════
EPIC #{epic_idx} (stratégie : {strategy})
══════════════════════════════════════════════════════════════
Titre       : {epic['title']}
Description : {epic.get('description', '')}
{arch_section}
══════════════════════════════════════════════════════════════
RÈGLES
══════════════════════════════════════════════════════════════
- 2 à 8 stories selon la complexité de l'epic
- Une story = un seul objectif utilisateur
- Coupe VERTICALE obligatoire (UI + backend + DB si applicable)
- Indépendance INVEST : chaque story livrable seule
- Stratégie de découpage : {strategy}

══════════════════════════════════════════════════════════════
FORMAT JSON ATTENDU (sans markdown)
══════════════════════════════════════════════════════════════
{{
  "stories": [
    {{
      "title": "En tant que [rôle précis], je veux [action concrète] afin de [bénéfice métier]",
      "description": "Contexte fonctionnel détaillé.",
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
    Génère les User Stories (sans SP ni AC) pour un seul epic.
    Retourne une liste de dicts { epic_id, title, description, story_points=0, acceptance_criteria=[], splitting_strategy }
    """
    prompt = _build_prompt(epic, epic_idx, architecture_details, missing_features, human_feedback)

    raw = await invoke_with_fallback(
        model      = _MODEL,
        messages   = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        max_tokens  = 2048,
        temperature = 0,
    )

    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"[generate] JSON invalide pour epic {epic_idx}: {e}\n{raw[:300]}")

    raw_stories = data.get("stories", [])
    if not raw_stories:
        raise ValueError(f"[generate] Aucune story pour epic {epic_idx}: {data}")

    result = []
    for i, s in enumerate(raw_stories):
        if not isinstance(s, dict):
            continue
        result.append({
            "epic_id":             epic_idx,
            "title":               str(s.get("title", f"Story {i + 1}")),
            "description":         str(s.get("description", "")),
            "story_points":        0,
            "acceptance_criteria": [],
            "splitting_strategy":  str(s.get("splitting_strategy",
                                              epic.get("splitting_strategy", "by_feature"))),
        })

    print(f"[generate]   Epic {epic_idx} → {len(result)} stories brutes")
    return result
