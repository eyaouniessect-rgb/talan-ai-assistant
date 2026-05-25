# models/pm/sprint.py
# Schéma PostgreSQL : project_management
#
# Table : sprints
# Persistance des sprints produits par le pipeline Staffing (Step 3 — Story
# Distribution). Unité de mesure : Story Points (pas d'heures).
#
# Chaque sprint est créé lors de la phase staffing avec status="planned",
# puis sync vers Jira (jira_sprint_id rempli), puis passe à "active"/"completed"
# au runtime via les webhooks Jira ou actions PM.

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Sprint(Base):
    __tablename__  = "sprints"
    __table_args__ = (
        UniqueConstraint("project_id", "sprint_number", name="uq_sprints_project_sprint_number"),
        {"schema": "project_management"},
    )

    id              = Column(Integer, primary_key=True)
    project_id      = Column(Integer, ForeignKey("crm.projects.id", ondelete="CASCADE"), nullable=False, index=True)
    sprint_number   = Column(Integer, nullable=False)          # 1, 2, 3 ...
    name            = Column(String,  nullable=False)          # "Sprint 1"
    start_date      = Column(Date,    nullable=False)          # planifié
    end_date        = Column(Date,    nullable=False)          # planifié
    # Dates réelles (clic PM) — celles envoyées à Jira et servent au burndown.
    actual_start_date = Column(Date, nullable=True)
    actual_end_date   = Column(Date, nullable=True)

    # Capacité cible & réalisée — Story Points (alignée avec story_distribution)
    target_capacity_sp = Column(Integer, nullable=False)
    actual_sp          = Column(Integer, nullable=False, default=0)

    # Cycle de vie du sprint pour le calcul du progress projet :
    # planned (par défaut) → active (sprint démarré) → completed (sprint terminé)
    status          = Column(String, nullable=False, default="planned")

    # ID du sprint Jira correspondant (rempli après sync Jira réussie).
    jira_sprint_id  = Column(Integer, nullable=True)

    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    project = relationship("Project", foreign_keys=[project_id])
