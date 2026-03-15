# Modèles SQLAlchemy pour le schéma RH (schema hris) :
# - `employees`    : id, name, email, role, team_id, manager_id
# - `leaves`       : id, employee_id, start_date, end_date, status, days_count
# - `teams`        : id, name, manager_id
# database/models/hris.py
# Modèles SQLAlchemy pour le schéma RH (schema hris)
# Tables :
# - employees : informations RH liées à un user
# - teams     : équipes
# - leaves    : demandes de congé

from sqlalchemy import Column, Integer, String, Date, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


# ─────────────────────────────────────────────
# Team
# ─────────────────────────────────────────────

class Team(Base):
    __tablename__ = "teams"
    __table_args__ = {"schema": "hris"}

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    # manager = user qui gère l'équipe
    manager_id = Column(Integer, ForeignKey("users.id"))

    # relations
    employees = relationship("Employee", back_populates="team")


# ─────────────────────────────────────────────
# Employee
# ─────────────────────────────────────────────

class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = {"schema": "hris"}

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("hris.teams.id"), nullable=False)

    skills = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="employee")
    team = relationship("Team", back_populates="employees")

    leaves = relationship(
        "Leave",
        back_populates="employee",
        cascade="all, delete-orphan"
    )

# ─────────────────────────────────────────────
# Leave
# ─────────────────────────────────────────────

class Leave(Base):
    __tablename__ = "leaves"
    __table_args__ = {"schema": "hris"}

    id = Column(Integer, primary_key=True)

    # employé qui demande le congé
    employee_id = Column(Integer, ForeignKey("hris.employees.id"))

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    days_count = Column(Integer)

    status = Column(String, default="pending")  # pending | approved | rejected

    created_at = Column(DateTime, server_default=func.now())

    # relation inverse
    employee = relationship("Employee", back_populates="leaves")