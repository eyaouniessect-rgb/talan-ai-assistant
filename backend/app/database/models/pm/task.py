# models/pm/task.py
# Schéma PostgreSQL : project_management
#
# Table : tasks
# Unité atomique d'exécution du pipeline. Règle métier : 1 tâche = 1 employé.
# assigned_employee_id rempli par le Staffing Agent (Phase 11) → hris.employees.id
# sprint_id rempli par le Sprint Planner (Phase 10).
# Champs CPM (earliest_start, latest_start, slack, is_critical) calculés en Phase 9.
# jira_task_key rempli après sync Jira en tant que sous-tâche (Phase 7).

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database.connection import Base
from .enums import TaskStatusEnum, TaskTypeEnum


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = {"schema": "project_management"}

    id                   = Column(Integer, primary_key=True)
    user_story_id        = Column(Integer, ForeignKey("project_management.user_stories.id"), nullable=False)
    title                = Column(String, nullable=False)
    type                 = Column(
        SAEnum(TaskTypeEnum, name="tasktypeenum",
               schema="project_management", native_enum=False),
        nullable=True,
    )

    # Durée estimée en heures — base du calcul CPM en Phase 9
    estimated_hours      = Column(Float, nullable=True)

    status               = Column(
        SAEnum(TaskStatusEnum, name="taskstatusenum",
               schema="project_management", native_enum=False),
        nullable=False,
        default=TaskStatusEnum.TODO,
    )

    # Employé assigné par le Staffing Agent — référence hris.employees (profil complet)
    assigned_employee_id = Column(Integer, ForeignKey("hris.employees.id"), nullable=True)

    # Sprint affecté par le Sprint Planner (Phase 10)
    sprint_id            = Column(Integer, ForeignKey("project_management.sprints.id"), nullable=True)

    # ── Champs CPM (Critical Path Method — Phase 9) ──
    # ES/LS en heures depuis le début du projet
    earliest_start       = Column(Float, nullable=True)
    latest_start         = Column(Float, nullable=True)
    # slack = 0 signifie que la tâche est sur le chemin critique
    slack                = Column(Float, nullable=True)
    is_critical          = Column(Boolean, default=False, nullable=False)

    jira_task_key        = Column(String, nullable=True)

    # Métadonnées IA : score de staffing, alternatives d'assignation, raisonnement
    ai_metadata          = Column(JSONB, nullable=True)

    created_at           = Column(DateTime, server_default=func.now())

    user_story   = relationship("UserStory", back_populates="tasks")
    sprint       = relationship("Sprint", back_populates="tasks")
    employee     = relationship("Employee", foreign_keys=[assigned_employee_id])
    dependencies = relationship(
        "TaskDependency",
        foreign_keys="[TaskDependency.task_id]",
        back_populates="task",
        cascade="all, delete-orphan",
    )
