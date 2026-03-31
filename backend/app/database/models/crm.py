# database/models/crm.py
# Tables :
# - clients     : clients de Talan
# - projects    : projets avec start_date + end_date
# - assignments : participation d'un employé à un projet
#                 (remplace project_members — ajoute allocation_percent, start/end date)

from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = {"schema": "crm"}

    id            = Column(Integer, primary_key=True)
    name          = Column(String, nullable=False)
    industry      = Column(String)
    contact_email = Column(String)

    projects = relationship("Project", back_populates="client", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"schema": "crm"}

    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False)
    client_id  = Column(Integer, ForeignKey("crm.clients.id"), nullable=False)
    status     = Column(String, default="En cours")   # En cours | Terminé | En attente
    progress   = Column(Float, default=0.0)           # 0.0 → 100.0
    start_date = Column(Date, nullable=True)
    end_date   = Column(Date, nullable=True)          # remplace deadline
    created_at = Column(DateTime, server_default=func.now())

    client      = relationship("Client", back_populates="projects")
    assignments = relationship("Assignment", back_populates="project", cascade="all, delete-orphan")


class Assignment(Base):
    """Participation d'un employé à un projet.
    Règle métier : la somme des allocation_percent actifs d'un employé ≤ 100.
    Cette contrainte est vérifiée côté application (pas en DB).
    """
    __tablename__ = "assignments"
    __table_args__ = {"schema": "crm"}

    id                 = Column(Integer, primary_key=True)
    project_id         = Column(Integer, ForeignKey("crm.projects.id"),    nullable=False)
    employee_id        = Column(Integer, ForeignKey("hris.employees.id"),  nullable=False)
    role_in_project    = Column(String)                # ex: "Lead Dev", "Designer", "DevOps"
    allocation_percent = Column(Integer, default=100)  # % du temps alloué au projet
    start_date         = Column(Date, nullable=True)
    end_date           = Column(Date, nullable=True)   # NULL = encore affecté
    joined_at          = Column(DateTime, server_default=func.now())

    project  = relationship("Project", back_populates="assignments")
    employee = relationship("Employee")
