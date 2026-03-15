# Modèles SQLAlchemy pour le schéma CRM (schema crm) :
# - `clients`      : id, name, industry, contact_email
# - `projects`     : id, name, client_id, status, progress, deadline, team_ids
# - `reports`      : id, project_id, content, generated_at

# database/models/crm.py
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

    projects = relationship(
        "Project",
        back_populates="client",
        cascade="all, delete-orphan"
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"schema": "crm"}

    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False)
    client_id  = Column(Integer, ForeignKey("crm.clients.id"), nullable=False)
    status     = Column(String, default="En cours")
    progress   = Column(Float, default=0.0)
    deadline   = Column(Date)
    created_at = Column(DateTime, server_default=func.now())

    client  = relationship("Client", back_populates="projects")
    members = relationship(
        "ProjectMember",
        back_populates="project",
        cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = {"schema": "crm"}

    id              = Column(Integer, primary_key=True)
    project_id      = Column(Integer, ForeignKey("crm.projects.id"), nullable=False)
    employee_id     = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    role_in_project = Column(String)        # ex: "Lead Dev", "Designer", "DevOps"
    joined_at       = Column(DateTime, server_default=func.now())

    project  = relationship("Project", back_populates="members")
    employee = relationship("Employee")