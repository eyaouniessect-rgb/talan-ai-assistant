# models/crm/project.py
# Schéma PostgreSQL : crm
#
# Table : projects
# Représente un projet Talan pour un client donné.
# project_manager_id → hris.employees.id : le PM est un employé avec un profil RH complet.
# Référencé par pm.epics, pm.pipeline_state et pm.sprints pour le pipeline IA.

from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"schema": "crm"}

    id                 = Column(Integer, primary_key=True)
    name               = Column(String, nullable=False)
    client_id          = Column(Integer, ForeignKey("crm.clients.id"), nullable=False)
    status             = Column(String, default="En cours")   # En cours | Terminé | En attente
    progress           = Column(Float, default=0.0)           # 0.0 → 100.0
    start_date         = Column(Date, nullable=True)
    end_date           = Column(Date, nullable=True)

    # PM responsable — FK vers hris.employees (cohérent avec crm.assignments)
    # Dashboard PM : SELECT * FROM crm.projects WHERE project_manager_id = employee.id
    project_manager_id = Column(Integer, ForeignKey("hris.employees.id"), nullable=True)

    created_at         = Column(DateTime, server_default=func.now())

    client          = relationship("Client", back_populates="projects")
    project_manager = relationship("Employee", foreign_keys=[project_manager_id])
    assignments     = relationship("Assignment", back_populates="project", cascade="all, delete-orphan")
