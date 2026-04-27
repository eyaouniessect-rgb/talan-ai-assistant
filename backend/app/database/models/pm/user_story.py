# models/pm/user_story.py
# Schéma PostgreSQL : project_management
#
# Table : user_stories
# Une user story = une fonctionnalité du point de vue utilisateur.
# Générée en Phase 3 (IA) ou ajoutée manuellement.
# priority rempli en Phase 6 (MoSCoW : must_have | should_have | could_have | wont_have).
# jira_issue_key rempli après validation + sync Jira.

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database.connection import Base
from .enums import StoryStatusEnum


class UserStory(Base):
    __tablename__ = "user_stories"
    __table_args__ = {"schema": "project_management"}

    id                  = Column(Integer, primary_key=True)
    epic_id             = Column(Integer, ForeignKey("project_management.epics.id"), nullable=False)
    title               = Column(String, nullable=False)
    description         = Column(Text, nullable=True)

    # Estimation de complexité en suite de Fibonacci (1, 2, 3, 5, 8, 13, 21)
    story_points        = Column(Integer, nullable=True)

    # Priorité MoSCoW issue de la Phase 6
    priority            = Column(String, nullable=True)

    status              = Column(
        SAEnum(StoryStatusEnum, name="storystatusenum",
               schema="project_management", native_enum=False),
        nullable=False,
        default=StoryStatusEnum.GENERATED,
    )

    acceptance_criteria = Column(Text, nullable=True)

    # Stratégie de découpage choisie par l'IA (ex: "par workflow", "par rôle utilisateur")
    splitting_strategy  = Column(String, nullable=True)

    jira_issue_key      = Column(String, nullable=True)
    ai_metadata         = Column(JSONB, nullable=True)
    created_at          = Column(DateTime, server_default=func.now())

    epic         = relationship("Epic", back_populates="user_stories")
    tasks        = relationship("Task", back_populates="user_story", cascade="all, delete-orphan")
    dependencies = relationship(
        "StoryDependency",
        foreign_keys="[StoryDependency.story_id]",
        back_populates="story",
        cascade="all, delete-orphan",
    )
