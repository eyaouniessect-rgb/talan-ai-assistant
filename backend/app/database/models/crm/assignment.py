# models/crm/assignment.py
# Schéma PostgreSQL : crm
#
# Table : assignments
# Participation d'un employé à un projet (vue macro).
# Règle métier : la somme des allocation_percent actifs d'un employé ≤ 100.
# Cette contrainte est vérifiée côté application (pas en DB).
# Distinct de pm.tasks.assigned_employee_id qui est la vue micro (1 tâche = 1 employé).

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = {"schema": "crm"}

    id                 = Column(Integer, primary_key=True)
    project_id         = Column(Integer, ForeignKey("crm.projects.id"), nullable=False)
    employee_id        = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    role_in_project    = Column(String, nullable=True)     # ex: "Lead Dev", "Designer", "DevOps"
    allocation_percent = Column(Integer, default=100)      # % du temps alloué au projet
    start_date         = Column(Date, nullable=True)
    end_date           = Column(Date, nullable=True)       # NULL = encore affecté
    joined_at          = Column(DateTime, server_default=func.now())

    project  = relationship("Project", back_populates="assignments")
    employee = relationship("Employee", foreign_keys=[employee_id])
