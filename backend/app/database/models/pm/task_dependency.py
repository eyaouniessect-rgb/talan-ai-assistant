# models/pm/task_dependency.py
# Schéma PostgreSQL : project_management
#
# Table : task_dependencies
# Graphe de dépendances entre tâches (Phase 8 — Dependency Agent).
# Utilisé en Phase 9 pour calculer le chemin critique (CPM).
# Contrainte unique pour éviter les doublons dans le graphe.

from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.connection import Base


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependency"),
        {"schema": "project_management"},
    )

    task_id            = Column(Integer, ForeignKey("project_management.tasks.id"), primary_key=True)
    depends_on_task_id = Column(Integer, ForeignKey("project_management.tasks.id"), primary_key=True)

    task       = relationship("Task", foreign_keys=[task_id], back_populates="dependencies")
    depends_on = relationship("Task", foreign_keys=[depends_on_task_id])
