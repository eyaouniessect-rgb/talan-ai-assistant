# agents/pm/agents/stories/prompt.py
# Phase 3 — User Stories + acceptance_criteria
#
# Deux modes selon la disponibilité du VLM :
#   - architecture_details fourni  → stories alignées sur les composants détectés
#   - architecture_details absent  → découpage purement fonctionnel depuis le CDC

STORIES_SYSTEM_PROMPT = """Tu es un expert Agile (Product Owner senior) avec 15 ans d'expérience.
Tu décomposes des epics en User Stories au bon niveau de granularité.
Tu génères des critères d'acceptation précis, testables et mesurables.
Réponds UNIQUEMENT avec du JSON valide, sans markdown."""


# ──────────────────────────────────────────────────────────────
# RÈGLES DE GRANULARITÉ (injectées dans chaque prompt)
# ──────────────────────────────────────────────────────────────

_GRANULARITY_RULES = """
══════════════════════════════════════════════════════════════
RÈGLES DE GRANULARITÉ — À RESPECTER STRICTEMENT
══════════════════════════════════════════════════════════════

1. UNE STORY = UN SEUL OBJECTIF UTILISATEUR
   ✓ "En tant qu'utilisateur, je veux uploader mon CV pour démarrer le matching"
   ✗ "En tant qu'utilisateur, je veux gérer mon profil" (trop large → diviser)

2. TAILLE PAR STORY_POINTS (Fibonacci)
   • 1-2 pts  : tâche simple, un seul écran / un seul endpoint
   • 3-5 pts  : fonctionnalité complète avec UI + logique métier
   • 8 pts    : fonctionnalité complexe — à découper si possible
   • 13 pts   : INTERDIT — toute story à 13 doit être divisée en 2-3 stories
   → Cible : 80% des stories entre 2 et 5 points

3. COUPE VERTICALE OBLIGATOIRE
   Chaque story doit traverser toutes les couches nécessaires (UI + backend + DB).
   Ne jamais créer "une story frontend" + "une story backend" pour la même fonctionnalité.

4. INDÉPENDANCE (principe INVEST)
   Chaque story doit être livrable indépendamment des autres.
   Si story B ne peut pas exister sans story A → A est un prérequis, pas une story séparée.

5. VOLUME PAR EPIC
   • Petit epic (1-2 fonctionnalités) : 2 à 4 stories
   • Epic moyen (3-5 fonctionnalités) : 4 à 7 stories
   • Grand epic (6+ fonctionnalités)  : 6 à 10 stories, mais reconsidérer le découpage

6. CRITÈRES D'ACCEPTATION
   • 3 à 5 critères par story
   • Format : "Étant donné [contexte], quand [action], alors [résultat mesurable]"
   • Chaque critère doit être testable automatiquement ou manuellement
   • Inclure au moins 1 critère négatif (cas d'erreur)
"""


# ──────────────────────────────────────────────────────────────
# SECTION ARCHITECTURE (injectée si VLM a détecté une archi)
# ──────────────────────────────────────────────────────────────

def _build_architecture_section(details: dict) -> str:
    """
    Construit la section architecture à injecter dans le prompt.
    Utilisée uniquement si architecture_detected = True.
    """
    lines = [
        "══════════════════════════════════════════════════════════════",
        "ARCHITECTURE DÉTECTÉE — ALIGNER LES STORIES SUR CES COMPOSANTS",
        "══════════════════════════════════════════════════════════════",
        f"Type : {details.get('architecture_type', 'inconnu')}",
        "",
        "⚠ RÈGLE CRITIQUE : chaque story qui implique un composant listé ci-dessous",
        "   doit nommer ce composant dans son titre ou sa description.",
        "   Ne jamais inventer des composants absents de cette liste.",
        "",
    ]

    layers = details.get("layers", [])
    if layers:
        lines.append("COUCHES :")
        for layer in layers:
            name       = layer.get("name", "")
            components = layer.get("components", [])
            techs      = layer.get("technologies", [])
            line = f"  • {name}"
            if components:
                line += f" → composants : {', '.join(components)}"
            if techs:
                line += f" | technologies : {', '.join(techs)}"
            lines.append(line)
        lines.append("")

    agents = details.get("agents", [])
    if agents:
        lines.append("AGENTS :")
        for a in agents:
            role = f" — {a['role']}" if a.get("role") else ""
            lines.append(f"  • {a['name']}{role}")
        lines.append("")

    data_sources = details.get("data_sources", [])
    if data_sources:
        lines.append(f"SOURCES DE DONNÉES : {', '.join(data_sources)}")

    protocols = details.get("communication_protocols", [])
    if protocols:
        lines.append(f"PROTOCOLES : {', '.join(protocols)}")

    external = details.get("external_services", [])
    if external:
        lines.append(f"SERVICES EXTERNES : {', '.join(external)}")

    lines.append("")
    lines.append("CONSIGNE : pour chaque story liée à un agent ou service ci-dessus,")
    lines.append("  précise le nom exact du composant dans la description.")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# STRATÉGIES DE DÉCOUPAGE
# ──────────────────────────────────────────────────────────────

_SPLITTING_GUIDE = """
GUIDE DE DÉCOUPAGE PAR STRATÉGIE :
  • by_feature       : 1 story par fonctionnalité distincte visible par l'utilisateur
  • by_user_role     : 1 story par type d'utilisateur (admin, user, guest…) pour la même fonctionnalité
  • by_workflow_step : 1 story par étape séquentielle du processus métier
  • by_component     : 1 story par composant/agent/service de l'architecture (utiliser si archi détectée)
"""


# ──────────────────────────────────────────────────────────────
# BUILDER PRINCIPAL
# ──────────────────────────────────────────────────────────────

def build_stories_prompt(
    epics:                list[dict],
    human_feedback:       str | None  = None,
    architecture_details: dict | None = None,
) -> str:
    """
    Construit le prompt user stories.

    Si architecture_details est fourni (VLM phase 1) → section architecture injectée
    pour aligner les stories sur les composants réels du système.
    """
    # ── Feedback PM ───────────────────────────────────────────
    feedback_section = (
        f"\n⚠ CORRECTIONS DU PM — intègre ces retours dans la nouvelle génération :\n"
        f"{human_feedback}\n"
    ) if human_feedback else ""

    # ── Architecture (optionnelle) ────────────────────────────
    arch_section = (
        "\n" + _build_architecture_section(architecture_details) + "\n"
    ) if architecture_details else (
        "\n[Aucune architecture détectée — découpage purement fonctionnel]\n"
    )

    # ── Epics formatés ────────────────────────────────────────
    epics_text = "\n".join([
        f"Epic {i} (stratégie: {e.get('splitting_strategy', 'by_feature')}) :\n"
        f"  Titre       : {e['title']}\n"
        f"  Description : {e.get('description', '')}"
        for i, e in enumerate(epics)
    ])

    return f"""Décompose ces epics en User Stories Agile prêtes pour le sprint planning.
{feedback_section}
{_GRANULARITY_RULES}
{_SPLITTING_GUIDE}
{arch_section}
══════════════════════════════════════════════════════════════
FORMAT JSON ATTENDU
══════════════════════════════════════════════════════════════
Retourne UNIQUEMENT ce JSON (sans markdown) :
{{
  "stories": [
    {{
      "epic_id": 0,
      "title": "En tant que [rôle précis], je veux [action concrète] afin de [bénéfice métier]",
      "description": "Contexte fonctionnel détaillé. Si un composant/agent est impliqué, le nommer explicitement.",
      "story_points": 3,
      "acceptance_criteria": [
        "Étant donné [contexte], quand [action], alors [résultat mesurable]",
        "Étant donné [contexte d'erreur], quand [action invalide], alors [message d'erreur attendu]"
      ],
      "splitting_strategy": "by_feature"
    }}
  ]
}}

══════════════════════════════════════════════════════════════
EPICS À DÉCOMPOSER
══════════════════════════════════════════════════════════════
{epics_text}"""
