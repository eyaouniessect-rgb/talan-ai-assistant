# agents/pm/agents/stories/prompt.py
# Phase 3 — User Stories + acceptance_criteria
# La splitting_strategy de chaque epic guide le découpage.

STORIES_SYSTEM_PROMPT = """Tu es un expert Agile (Product Owner senior).
Tu décomposes des epics en User Stories selon une stratégie de découpage fournie.
Tu génères aussi les critères d'acceptation (acceptance_criteria) pour chaque story.
Réponds UNIQUEMENT avec du JSON valide."""


def build_stories_prompt(epics: list[dict], human_feedback: str | None = None) -> str:
    feedback_section = f"\n⚠️ CORRECTIONS PM :\n{human_feedback}\n" if human_feedback else ""

    epics_text = "\n".join([
        f"Epic {i}: {e['title']} (stratégie: {e.get('splitting_strategy','by_feature')})\n  {e['description']}"
        for i, e in enumerate(epics)
    ])

    return f"""Décompose ces epics en User Stories Agile.
{feedback_section}
Pour chaque epic, utilise sa splitting_strategy pour adapter le découpage :
  - by_feature       : une story par fonctionnalité distincte
  - by_user_role     : une story par type d'utilisateur
  - by_workflow_step : une story par étape du processus
  - by_component     : une story par couche technique (front/back/infra/...)

Estime les story_points en suite de Fibonacci (1,2,3,5,8,13).
Génère 3 à 5 critères d'acceptation par story (testables et mesurables).

Retourne UNIQUEMENT ce JSON :
{{
  "stories": [
    {{
      "epic_id": 0,
      "title": "En tant que [rôle], je veux [action] afin de [bénéfice]",
      "description": "Détail fonctionnel",
      "story_points": 3,
      "acceptance_criteria": ["Critère 1", "Critère 2"],
      "splitting_strategy": "by_feature"
    }}
  ]
}}

Epics :
{epics_text}"""
