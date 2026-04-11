# models/pm/epic.py
# Schéma PostgreSQL : project_management
#
# Table : epics
# Un epic = un grand bloc fonctionnel du projet (ex: "Module Authentification").
# Généré en Phase 2 par l'Epic Generator Agent, validé par le PM.
# jira_epic_key rempli après validation + synchronisation Jira.

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database.connection import Base
from .enums import EpicStatusEnum


class Epic(Base):
    __tablename__ = "epics"
    __table_args__ = {"schema": "project_management"}

    id            = Column(Integer, primary_key=True)
    project_id    = Column(Integer, ForeignKey("crm.projects.id"), nullable=False)
    title         = Column(String, nullable=False)
    description   = Column(Text, nullable=True)

    # Stratégie de découpage des user stories pour cet epic.
    # Valeurs : "by_feature" | "by_user_role" | "by_workflow_step" | "by_component"
    # Déterminée par le LLM en Phase 2, utilisée par le node stories (Phase 3).
    splitting_strategy = Column(String, nullable=True, default="by_feature")

    status        = Column(
        SAEnum(EpicStatusEnum, name="epicstatusenum",
               schema="project_management", native_enum=False),
        nullable=False,
        default=EpicStatusEnum.DRAFT,
    )

    # Clé Jira créée après validation PM et sync (ex: "PROJ-E1")
    jira_epic_key = Column(String, nullable=True)

    # Métadonnées IA
    ai_metadata   = Column(JSONB, nullable=True)

    created_at    = Column(DateTime, server_default=func.now())

    project      = relationship("Project", foreign_keys=[project_id])
    user_stories = relationship("UserStory", back_populates="epic", cascade="all, delete-orphan")
