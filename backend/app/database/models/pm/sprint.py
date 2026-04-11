# models/pm/sprint.py
# Schéma PostgreSQL : project_management
#
# Table : sprints
# Un sprint = une itération de livraison (1 à 4 semaines).
# Créé en Phase 10 par le Sprint Planner Agent.
# capacity_hours = somme des heures disponibles de l'équipe sur la période.
# Utilisé par le Sprint Planner pour ne pas dépasser la vélocité.

from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Sprint(Base):
    __tablename__ = "sprints"
    __table_args__ = {"schema": "project_management"}

    id             = Column(Integer, primary_key=True)
    project_id     = Column(Integer, ForeignKey("crm.projects.id"), nullable=False)
    name           = Column(String, nullable=False)   # ex: "Sprint 1 — Authentification"
    start_date     = Column(Date, nullable=True)
    end_date       = Column(Date, nullable=True)

    # Capacité totale en heures — utilisée par le Sprint Planner pour l'affectation des tâches
    capacity_hours = Column(Float, nullable=True)

    created_at     = Column(DateTime, server_default=func.now())

    project = relationship("Project", foreign_keys=[project_id])
    tasks   = relationship("Task", back_populates="sprint")
