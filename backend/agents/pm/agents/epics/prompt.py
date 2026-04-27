# agents/pm/agents/epics/prompt.py
# ═══════════════════════════════════════════════════════════════
# Prompt de génération des Epics — Phase 2
#
# Le LLM doit :
#   1. Analyser le CDC et identifier les grandes fonctionnalités
#   2. Regrouper les fonctionnalités en epics cohérents
#   3. Pour chaque epic, détecter la splitting_strategy optimale
#      (utilisée en phase 3 pour découper en user stories)
#
# splitting_strategy values :
#   "by_feature"       — fonctionnalités distinctes dans l'epic
#   "by_user_role"     — types d'utilisateurs différents
#   "by_workflow_step" — étapes séquentielles d'un processus
#   "by_component"     — couches techniques (front/back/infra)
# ═══════════════════════════════════════════════════════════════


EPICS_SYSTEM_PROMPT = """Tu es un expert en gestion de projet Agile et en analyse de cahiers des charges.
Tu aides un Project Manager à décomposer un projet en epics LangGraph pour un pipeline de développement Scrum.

Règles absolues :
- Réponds UNIQUEMENT avec du JSON valide, sans texte avant ni après.
- Génère autant d'epics que nécessaire selon la taille et la complexité du projet.
- Chaque epic doit être autonome et livrable indépendamment.
- La splitting_strategy doit refléter la meilleure façon de découper CET epic en stories.
- Les descriptions doivent être en français et orientées valeur métier.
- Identifie les acteurs HUMAINS du domaine métier tels qu'ils apparaissent dans le CDC.
  Ces acteurs seront utilisés pour rédiger les User Stories en phase suivante.
  N'invente pas des acteurs génériques — déduis-les du contenu du CDC."""


def build_epics_prompt(cdc_text: str, human_feedback: str | None = None) -> str:
    """
    Construit le prompt utilisateur pour la génération des epics.

    Si human_feedback est fourni (phase rejetée par le PM),
    les corrections sont intégrées directement dans le prompt.
    """
    feedback_section = ""
    if human_feedback:
        feedback_section = f"""
⚠️ CORRECTIONS DEMANDÉES PAR LE PM :
{human_feedback}

Tu dois corriger les epics en tenant compte de ces remarques.
"""

    return f"""Analyse ce Cahier des Charges (CDC) et génère les epics du projet.

{feedback_section}
Pour chaque epic, détermine la splitting_strategy la plus appropriée :
  - "by_feature"       : l'epic contient des fonctionnalités distinctes
  - "by_user_role"     : différents types d'utilisateurs ont des besoins différents
  - "by_workflow_step" : l'epic suit un processus séquentiel (étape 1 → 2 → 3)
  - "by_component"     : l'epic concerne plusieurs couches techniques (front/back/infra)

Retourne UNIQUEMENT ce JSON (sans markdown, sans explication) :
{{
  "business_actors": [
    "<rôle humain déduit du CDC>",
    "<rôle humain déduit du CDC>",
    "..."
  ],
  "epics": [
    {{
      "title": "Titre court et explicite de l'epic",
      "description": "Description fonctionnelle orientée valeur métier (2-4 phrases)",
      "splitting_strategy": "by_feature|by_user_role|by_workflow_step|by_component"
    }}
  ]
}}

Règles pour "business_actors" :
- Déduis les acteurs UNIQUEMENT depuis le contenu du CDC (pas d'invention)
- Rôles humains réels uniquement (jamais "système", "API", "backend", "base de données", "application")
- Entre 2 et 8 acteurs selon la richesse du CDC

CDC à analyser :
{cdc_text}"""
