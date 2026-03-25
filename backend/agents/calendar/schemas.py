from a2a.types import AgentCard, AgentSkill, AgentCapabilities


# ══════════════════════════════════════════════════
# SKILLS CALENDAR AGENT
# ══════════════════════════════════════════════════

skill_check_calendar_conflicts = AgentSkill(
    id="check_calendar_conflicts",
    name="Vérifier la disponibilité",
    description="Vérifie les créneaux occupés dans le calendrier pour détecter les conflits.",
    tags=["calendar", "disponibilité", "conflits"],
    examples=[
        "Suis-je disponible demain ?",
        "Vérifie mon calendrier du 20 au 25 avril",
        "Y a-t-il des conflits cette semaine ?",
    ],
)

skill_get_calendar_events = AgentSkill(
    id="get_calendar_events",
    name="Consulter les événements",
    description="Retourne la liste des événements du calendrier sur une période donnée.",
    tags=["calendar", "événements"],
    examples=[
        "Montre mes événements cette semaine",
        "Quels sont mes rendez-vous demain ?",
    ],
)

skill_create_meeting = AgentSkill(
    id="create_meeting",
    name="Créer une réunion",
    description="Crée un événement dans le calendrier avec une date et un titre.",
    tags=["calendar", "création", "réunion"],
    examples=[
        "Planifie une réunion demain à 10h",
        "Crée un meeting avec l'équipe lundi",
    ],
)

skill_update_meeting = AgentSkill(
    id="update_meeting",
    name="Modifier une réunion",
    description="Modifie un événement existant dans le calendrier.",
    tags=["calendar", "modification"],
    examples=[
        "Change le titre de ma réunion",
        "Décale mon meeting de demain",
    ],
)

skill_delete_meeting = AgentSkill(
    id="delete_meeting",
    name="Supprimer une réunion",
    description="Supprime un événement du calendrier.",
    tags=["calendar", "suppression"],
    examples=[
        "Supprime ma réunion de demain",
        "Annule mon meeting",
    ],
)

skill_search_meetings = AgentSkill(
    id="search_meetings",
    name="Rechercher des événements",
    description="Recherche des événements dans le calendrier à partir d'un mot-clé.",
    tags=["calendar", "recherche"],
    examples=[
        "Cherche réunion projet",
        "Trouve mes meetings avec Ahmed",
    ],
)


# ══════════════════════════════════════════════════
# AGENT CARD
# ══════════════════════════════════════════════════

def build_agent_card(host: str, port: int) -> AgentCard:
    return AgentCard(
        name="CalendarAgent",
        description="Agent spécialisé dans la gestion du calendrier : événements, disponibilités et réunions.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            skill_check_calendar_conflicts,
            skill_get_calendar_events,
            skill_create_meeting,
            skill_update_meeting,
            skill_delete_meeting,
            skill_search_meetings,
        ],
    )