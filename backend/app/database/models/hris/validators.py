# models/hris/validators.py
# Schéma PostgreSQL : hris
#
# Schémas Pydantic pour les tables du schéma hris.
# Utilisés pour la validation des requêtes API et la sérialisation des réponses.

from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional
from .enums import SeniorityEnum, SkillLevelEnum, LeaveTypeEnum, LeaveStatusEnum


# ─────────────────────────────────────────────
# Employee
# ─────────────────────────────────────────────

class EmployeeResponse(BaseModel):
    id: int
    user_id: int
    team_id: int
    job_title: Optional[str] = None
    phone: Optional[str] = None
    seniority: Optional[SeniorityEnum] = None
    hire_date: Optional[date] = None
    leave_balance: int

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# Leave
# ─────────────────────────────────────────────

class LeaveCreate(BaseModel):
    leave_type: LeaveTypeEnum
    start_date: date
    end_date: date
    justification_url: Optional[str] = None


class LeaveResponse(BaseModel):
    id: int
    employee_id: int
    leave_type: LeaveTypeEnum
    start_date: date
    end_date: date
    days_count: Optional[int] = None
    status: LeaveStatusEnum
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# Skill
# ─────────────────────────────────────────────

class SkillResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class EmployeeSkillResponse(BaseModel):
    skill_id: int
    skill_name: str
    level: Optional[SkillLevelEnum] = None

    model_config = {"from_attributes": True}
