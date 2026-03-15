# Schémas Pydantic pour les entrées/sorties de l'Agent RH :
# CreateLeaveRequest, LeaveResponse, TeamAvailabilityResponse
# agents/rh/schemas.py
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
    name="Créer un congé",
    description="Crée une demande de congé pour un employé.",
    tags=["rh", "congé"],
    examples=[
        "Je voudrais créer un congé du 15 au 21 mars",
        "Pose-moi un congé pour la semaine prochaine",
    ],
)

skill_get_my_leaves = AgentSkill(
    id="get_my_leaves",
    name="Consulter mes congés",
    description="Retourne la liste des congés d'un employé.",
    tags=["rh", "congé"],
    examples=[
        "Combien de jours de congé il me reste ?",
        "Montre-moi mes congés",
    ],
)

skill_get_team_availability = AgentSkill(
    id="get_team_availability",
    name="Disponibilité de l'équipe",
    description="Retourne la disponibilité des membres d'une équipe.",
    tags=["rh", "équipe", "disponibilité"],
    examples=[
        "Qui est disponible la semaine prochaine ?",
        "Disponibilité de mon équipe en avril",
    ],
)

skill_get_team_stack = AgentSkill(
    id="get_team_stack",
    name="Compétences de l'équipe",
    description="Retourne les compétences techniques des membres de l'équipe.",
    tags=["rh", "compétences"],
    examples=[
        "Quelles sont les compétences de mon équipe ?",
        "Qui sait faire du React dans l'équipe ?",
    ],
)

def build_agent_card(host: str, port: int) -> AgentCard:
    return AgentCard(
        name="RHAgent",
        description="Agent spécialisé dans la gestion RH : congés, disponibilités, compétences.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            skill_create_leave,
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
    status: str           # pending | approved | rejected

class TeamMemberAvailability(BaseModel):
    employee_name: str
    available: bool
    leave_dates: Optional[str] = None

class TeamAvailabilityResponse(BaseModel):
    members: list[TeamMemberAvailability]

class TeamStackResponse(BaseModel):
    members: list[dict]   # [{"name": "Eya", "skills": "Python, React"}]