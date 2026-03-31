from a2a.types import AgentCard, AgentSkill, AgentCapabilities


# ══════════════════════════════════════════════════
# SKILLS CALENDAR AGENT
# ══════════════════════════════════════════════════

skill_check_calendar_conflicts = AgentSkill(
    id="check_calendar_conflicts",
    name="Vérifier la disponibilité / détecter les conflits",
    description=(
        "Vérifie les créneaux occupés dans le calendrier pour détecter les conflits. "
        "Permet de savoir si un créneau est libre avant de planifier."
    ),
    tags=[
        "calendar", "disponibilité", "disponibilite", "conflits",
        "créneau libre", "creneau libre", "est-ce que je suis libre",
        "suis-je disponible", "est-il libre", "vérifier disponibilité",
        "créneau disponible", "slot libre", "free slot",
    ],
    examples=[
        "Suis-je disponible demain à 10h ?",
        "Vérifie mon calendrier du 20 au 25 avril",
        "Y a-t-il des conflits cette semaine ?",
        "Est-ce que Ahmed est libre mardi pour un point ?",
        "J'ai un créneau libre demain matin ?",
        "Vérifie si je suis occupé lundi après-midi",
    ],
)

skill_get_calendar_events = AgentSkill(
    id="get_calendar_events",
    name="Consulter les événements du calendrier",
    description=(
        "Retourne la liste des événements, réunions et rendez-vous "
        "du calendrier sur une période donnée."
    ),
    tags=[
        "calendar", "événements", "evenements", "agenda", "calendrier",
        "rendez-vous", "rendez vous", "planning", "programme",
        "emploi du temps", "mes événements", "quoi de prévu",
        "qu'est-ce que j'ai", "my events", "schedule",
    ],
    examples=[
        "Montre mes événements cette semaine",
        "Quels sont mes rendez-vous demain ?",
        "Qu'est-ce que j'ai de prévu lundi ?",
        "Mon agenda de la semaine prochaine",
        "Mon planning de demain",
        "C'est quoi mon programme aujourd'hui ?",
    ],
)

skill_create_meeting = AgentSkill(
    id="create_meeting",
    name="Créer une réunion / un événement",
    description=(
        "Crée un événement ou une réunion dans le calendrier Google. "
        "Supporte les réunions avec participants, Google Meet, et lieu."
    ),
    tags=[
        "calendar", "créer réunion", "creer reunion", "création",
        "réunion", "reunion", "meeting", "événement", "evenement",
        "planifier", "organiser", "programmer", "caler", "fixer",
        "google meet", "meet", "visio", "visioconférence",
        "call", "appel", "point", "stand-up", "standup",
        "sync", "one-on-one", "1-1", "kick-off",
    ],
    examples=[
        "Planifie une réunion demain à 10h",
        "Crée un meeting avec l'équipe lundi",
        "Organise un point avec Ahmed demain à 14h",
        "Cale-moi un call avec le client jeudi matin",
        "Crée un stand-up quotidien à 9h30",
        "Programme une visio avec l'équipe vendredi",
        "Fixe une réunion de 30 minutes avec Sara",
    ],
)

skill_update_meeting = AgentSkill(
    id="update_meeting",
    name="Modifier / déplacer une réunion",
    description=(
        "Modifie un événement existant : changer l'heure, la date, "
        "le titre, les participants ou le lieu."
    ),
    tags=[
        "calendar", "modifier", "modification", "déplacer", "deplacer",
        "décaler", "decaler", "reporter", "repousser", "avancer",
        "changer heure", "changer date", "mettre à jour",
        "reschedule", "update", "move",
    ],
    examples=[
        "Change le titre de ma réunion",
        "Décale mon meeting de demain à 15h",
        "Reporte la réunion de lundi à mercredi",
        "Avance le call de 14h à 13h",
        "Déplace ma réunion avec Ahmed à jeudi",
        "Change l'heure du stand-up à 10h",
    ],
)

skill_delete_meeting = AgentSkill(
    id="delete_meeting",
    name="Supprimer / annuler une réunion",
    description=(
        "Supprime ou annule un événement du calendrier."
    ),
    tags=[
        "calendar", "supprimer", "suppression", "annuler", "annulation",
        "enlever", "retirer", "cancel", "delete", "remove",
    ],
    examples=[
        "Supprime ma réunion de demain",
        "Annule mon meeting de lundi",
        "Enlève le call de 14h",
        "Annule la réunion avec le client",
        "Supprime tous mes événements de vendredi",
    ],
)

skill_search_meetings = AgentSkill(
    id="search_meetings",
    name="Rechercher des événements",
    description=(
        "Recherche des événements dans le calendrier par mot-clé, "
        "participant ou sujet."
    ),
    tags=[
        "calendar", "rechercher", "chercher", "trouver", "search",
        "find", "quand est", "où est", "retrouver",
    ],
    examples=[
        "Cherche réunion projet Alpha",
        "Trouve mes meetings avec Ahmed",
        "Quand est ma prochaine réunion d'équipe ?",
        "Recherche les événements avec le mot 'sprint'",
        "Retrouve le call avec le client de la semaine dernière",
    ],
)


# ══════════════════════════════════════════════════
# AGENT CARD
# ══════════════════════════════════════════════════

def build_agent_card(host: str, port: int) -> AgentCard:
    return AgentCard(
        name="CalendarAgent",
        description=(
            "Agent spécialisé dans la gestion du calendrier Google : "
            "consultation d'agenda et événements, création/modification/suppression "
            "de réunions et meetings, vérification de disponibilité et conflits, "
            "recherche d'événements par mot-clé."
        ),
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