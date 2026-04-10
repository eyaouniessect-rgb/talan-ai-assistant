# models/crm/validators.py
# Schéma PostgreSQL : crm
#
# Schémas Pydantic pour les tables du schéma crm.
# Utilisés pour la validation des requêtes API et la sérialisation des réponses.

from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


# ─────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────

class ClientResponse(BaseModel):
    id: int
    name: str
    industry: Optional[str] = None
    contact_email: Optional[str] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    client_id: int
    project_manager_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    client_id: int
    status: str
    progress: float
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    project_manager_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# Assignment
# ─────────────────────────────────────────────

class AssignmentCreate(BaseModel):
    project_id: int
    employee_id: int
    role_in_project: Optional[str] = None
    allocation_percent: int = 100
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class AssignmentResponse(BaseModel):
    id: int
    project_id: int
    employee_id: int
    role_in_project: Optional[str] = None
    allocation_percent: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    model_config = {"from_attributes": True}
