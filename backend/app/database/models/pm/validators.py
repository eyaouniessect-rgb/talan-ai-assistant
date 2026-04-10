# models/pm/validators.py
# Schéma PostgreSQL : project_management
#
# Schémas Pydantic pour les tables du schéma project_management.
# Utilisés pour la validation des requêtes API et la sérialisation des réponses
# du pipeline IA (dashboard PM, human-in-the-loop).

from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, Any
from .enums import (
    EpicStatusEnum, StoryStatusEnum, TaskStatusEnum,
    TaskTypeEnum, PipelinePhaseEnum, PipelineStatusEnum,
)


# ─────────────────────────────────────────────
# PipelineState
# ─────────────────────────────────────────────

class PipelineStateResponse(BaseModel):
    id: int
    project_id: int
    phase: PipelinePhaseEnum
    status: PipelineStatusEnum
    ai_output: Optional[Any] = None
    pm_comment: Optional[str] = None
    validated_by: Optional[int] = None
    validated_at: Optional[datetime] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class PipelineValidation(BaseModel):
    # Payload envoyé par le PM pour valider ou rejeter une phase
    status: PipelineStatusEnum     # validated | rejected
    pm_comment: Optional[str] = None


# ─────────────────────────────────────────────
# Epic
# ─────────────────────────────────────────────

class EpicResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: Optional[str] = None
    status: EpicStatusEnum
    jira_epic_key: Optional[str] = None
    ai_metadata: Optional[Any] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# UserStory
# ─────────────────────────────────────────────

class UserStoryResponse(BaseModel):
    id: int
    epic_id: int
    title: str
    description: Optional[str] = None
    story_points: Optional[int] = None
    priority: Optional[str] = None
    status: StoryStatusEnum
    acceptance_criteria: Optional[str] = None
    splitting_strategy: Optional[str] = None
    jira_issue_key: Optional[str] = None
    ai_metadata: Optional[Any] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# Sprint
# ─────────────────────────────────────────────

class SprintResponse(BaseModel):
    id: int
    project_id: int
    name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    capacity_hours: Optional[float] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# Task
# ─────────────────────────────────────────────

class TaskResponse(BaseModel):
    id: int
    user_story_id: int
    title: str
    type: Optional[TaskTypeEnum] = None
    estimated_hours: Optional[float] = None
    status: TaskStatusEnum
    assigned_employee_id: Optional[int] = None
    sprint_id: Optional[int] = None
    earliest_start: Optional[float] = None
    latest_start: Optional[float] = None
    slack: Optional[float] = None
    is_critical: bool
    jira_task_key: Optional[str] = None
    ai_metadata: Optional[Any] = None

    model_config = {"from_attributes": True}
