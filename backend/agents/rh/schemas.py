# agents/rh/schemas.py
# ═══════════════════════════════════════════════════════════
# AgentCard A2A + Modèles Pydantic
# ═══════════════════════════════════════════════════════════
# IMPORTANT : les skill IDs doivent correspondre EXACTEMENT
# aux valeurs dans app/a2a/discovery.py → INTENT_TO_SKILL
# C'est le lien entre le dynamic discovery et les agents.

import os
from a2a.types import AgentCard, AgentSkill, AgentCapabilities
from pydantic import BaseModel
from typing import Optional
from datetime import date

# ══════════════════════════════════════════════════
# PARTIE 1 — Identité A2A (AgentCard + AgentSkills)
# ══════════════════════════════════════════════════

skill_create_leave = AgentSkill(
    id="create_leave",
    name="Créer un congé / déclarer une absence",
    description=(
        "Crée une demande de congé (annuel, maladie, sans solde) ou enregistre "
        "une absence. Couvre aussi les déclarations implicites d'absence."
    ),
    tags=[
        "rh", "congé", "conge", "leave", "absence", "absent",
        "jour off", "repos", "malade", "maladie", "arrêt maladie",
        "arret maladie", "pas au bureau", "je ne viens pas",
        "je serai absent", "je suis absent", "je reste à la maison",
        "rester a la maison", "absent demain", "absent lundi",
        "poser un congé", "poser un jour", "day off",
    ],
    examples=[
        "Je voudrais créer un congé du 15 au 21 mars",
        "Pose-moi un congé pour la semaine prochaine",
        "Je serai absent lundi",
        "Je suis malade, je ne viens pas demain",
        "Pose-moi un jour off vendredi",
        "Je reste à la maison demain",
        "Je ne serai pas au bureau la semaine prochaine",
        "Arrêt maladie du 10 au 14 avril",
        "Je veux poser un jour de repos mercredi",
    ],
)

skill_check_leave_balance = AgentSkill(
    id="check_leave_balance",
    name="Vérifier le solde de congés",
    description=(
        "Vérifie le nombre de jours de congé restants pour un employé. "
        "Inclut le solde annuel, les jours consommés et les jours disponibles."
    ),
    tags=[
        "rh", "solde", "solde de congé", "solde de conge",
        "jours de congé", "jours de conge", "jours restants",
        "combien de jours", "reste de congé", "jours disponibles",
        "compteur congé", "balance leave", "leave balance",
    ],
    examples=[
        "Combien de jours de congé il me reste ?",
        "Mon solde de congés",
        "Combien de jours j'ai encore ?",
        "Quel est mon solde de congé annuel ?",
        "Il me reste combien de jours ?",
        "Jours de congé disponibles",
    ],
)

skill_get_my_leaves = AgentSkill(
    id="get_my_leaves",
    name="Consulter mes congés",
    description=(
        "Retourne la liste des congés d'un employé : en attente, approuvés, "
        "refusés. Permet de voir l'historique et le statut des demandes."
    ),
    tags=[
        "rh", "mes congés", "mes conges", "liste congés",
        "congés en attente", "congés approuvés", "historique congé",
        "mes absences", "demandes de congé", "statut congé",
        "mes demandes", "my leaves",
    ],
    examples=[
        "Montre-moi mes congés",
        "Mes congés en attente",
        "Liste de mes demandes de congé",
        "Est-ce que mon congé a été approuvé ?",
        "Quels congés j'ai posés ce mois ?",
        "Historique de mes absences",
    ],
)

skill_get_team_availability = AgentSkill(
    id="get_team_availability",
    name="Disponibilité de l'équipe",
    description=(
        "Retourne la disponibilité des membres d'une équipe sur une période. "
        "Montre qui est en congé, absent, ou disponible."
    ),
    tags=[
        "rh", "équipe", "equipe", "disponibilité", "disponibilite",
        "qui est disponible", "équipe disponible", "membres disponibles",
        "qui est absent", "qui est en congé", "absences équipe",
        "planning équipe", "team availability",
    ],
    examples=[
        "Qui est disponible la semaine prochaine ?",
        "Disponibilité de mon équipe en avril",
        "Qui est absent dans mon équipe cette semaine ?",
        "Qui est en congé la semaine prochaine ?",
        "Est-ce que quelqu'un est disponible lundi ?",
        "Planning des absences de l'équipe",
    ],
)

skill_delete_leave = AgentSkill(
    id="delete_leave",
    name="Supprimer / annuler une demande de congé",
    description=(
        "Supprime ou annule une demande de congé existante (en attente ou approuvée). "
        "Couvre aussi les formulations implicites comme 'je ne veux plus mon congé'."
    ),
    tags=[
        "rh", "congé", "conge", "leave", "absence",
        "supprimer congé", "supprimer conge", "annuler congé", "annuler conge",
        "supprimer demande", "annuler demande", "retirer congé", "retirer conge",
        "supprimer absence", "annuler absence",
        "cancel leave", "delete leave",
        "demande de congé", "demande de conge",
        "je ne veux plus", "annuler mon congé", "annuler mon conge",
        "supprimer mon congé", "supprimer mon conge",
    ],
    examples=[
        "Supprimer mon congé de demain",
        "Annuler ma demande de congé",
        "Je veux annuler mon congé de la semaine prochaine",
        "Supprime ma demande de congé du 20 mars",
        "Retire mon absence de lundi",
        "Je ne veux plus mon congé de demain",
        "Supprimer mon demande de congé demain",
    ],
)

skill_get_team_stack = AgentSkill(
    id="get_team_stack",
    name="Compétences techniques de l'équipe",
    description=(
        "Retourne les compétences techniques (stack) des membres de l'équipe. "
        "Permet de trouver qui maîtrise une technologie spécifique."
    ),
    tags=[
        "rh", "compétences", "competences", "stack", "technologies",
        "skills", "expertise", "qui sait faire", "qui maîtrise",
        "tech stack", "membres de l'équipe", "membres de mon équipe",
        "compétences de l'équipe", "competences de l'equipe",
    ],
    examples=[
        "Quelles sont les compétences de mon équipe ?",
        "Qui sait faire du React dans l'équipe ?",
        "Stack technique de mon équipe",
        "Qui maîtrise Python dans l'équipe ?",
        "Compétences des membres de mon équipe",
        "Qui a de l'expérience en DevOps ?",
    ],
)

def build_agent_card(host: str, port: int) -> AgentCard:
    return AgentCard(
        name="RHAgent",
        description=(
            "Agent spécialisé dans la gestion des ressources humaines : "
            "création et suivi de congés, déclaration d'absences et maladies, "
            "consultation du solde de jours, disponibilité des membres de l'équipe, "
            "et compétences techniques de l'équipe."
        ),
        url=f"http://{host}:{port}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            skill_create_leave,
            skill_delete_leave,
            skill_check_leave_balance,
            skill_get_my_leaves,
            skill_get_team_availability,
            skill_get_team_stack,
        ],
    )

# ══════════════════════════════════════════════════
# PARTIE 2 — Modèles Pydantic (validation des données)
# ══════════════════════════════════════════════════

class CreateLeaveRequest(BaseModel):
    user_id: int
    start_date: date
    end_date: date

class LeaveResponse(BaseModel):
    id: int
    employee_id: int
    start_date: date
    end_date: date
    days_count: int
    status: str

class TeamMemberAvailability(BaseModel):
    employee_name: str
    available: bool
    leave_dates: Optional[str] = None

class TeamAvailabilityResponse(BaseModel):
    members: list[TeamMemberAvailability]

class TeamStackResponse(BaseModel):
    members: list[dict]