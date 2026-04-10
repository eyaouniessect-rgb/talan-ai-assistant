# models/pm/story_dependency.py
# Schéma PostgreSQL : project_management
#
# Table : story_dependencies
# Graphe de dépendances entre user stories (Phase 5 — Dependency Agent).
# Utilisé pour ordonner le backlog et synchroniser les liens Jira (LINK issues).
# Contrainte unique pour éviter les doublons dans le graphe.

from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.connection import Base


class StoryDependency(Base):
    __tablename__ = "story_dependencies"
    __table_args__ = (
        UniqueConstraint("story_id", "depends_on_story_id", name="uq_story_dependency"),
        {"schema": "project_management"},
    )

    story_id            = Column(Integer, ForeignKey("project_management.user_stories.id"), primary_key=True)
    depends_on_story_id = Column(Integer, ForeignKey("project_management.user_stories.id"), primary_key=True)

    story      = relationship("UserStory", foreign_keys=[story_id], back_populates="dependencies")
    depends_on = relationship("UserStory", foreign_keys=[depends_on_story_id])
