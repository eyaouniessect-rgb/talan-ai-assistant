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
    id="create_leave",           # ← doit matcher INTENT_TO_SKILL
    name="Créer un congé",
    description="Crée une demande de congé pour un employé.",
    tags=["rh", "congé"],
    examples=[
        "Je voudrais créer un congé du 15 au 21 mars",
        "Pose-moi un congé pour la semaine prochaine",
    ],
)

skill_check_leave_balance = AgentSkill(
    id="check_leave_balance",    # ← doit matcher INTENT_TO_SKILL
    name="Vérifier le solde de congés",
    description="Vérifie le solde de congés disponible d'un employé.",
    tags=["rh", "congé", "solde"],
    examples=[
        "Combien de jours de congé il me reste ?",
        "Mon solde de congés",
    ],
)

skill_get_my_leaves = AgentSkill(
    id="get_my_leaves",          # ← doit matcher INTENT_TO_SKILL
    name="Consulter mes congés",
    description="Retourne la liste des congés d'un employé.",
    tags=["rh", "congé"],
    examples=[
        "Montre-moi mes congés",
        "Mes congés en attente",
    ],
)

skill_get_team_availability = AgentSkill(
    id="get_team_availability",  # ← doit matcher INTENT_TO_SKILL
    name="Disponibilité de l'équipe",
    description="Retourne la disponibilité des membres d'une équipe.",
    tags=["rh", "équipe", "disponibilité"],
    examples=[
        "Qui est disponible la semaine prochaine ?",
        "Disponibilité de mon équipe en avril",
    ],
)

skill_get_team_stack = AgentSkill(
    id="get_team_stack",         # ← doit matcher INTENT_TO_SKILL
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
            skill_check_leave_balance,      # ← AJOUTÉ
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