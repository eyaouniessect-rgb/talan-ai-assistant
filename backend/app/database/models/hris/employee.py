# models/hris/employee.py
# Schéma PostgreSQL : hris
#
# Table : employees
# Profil RH d'un utilisateur (1 user = 1 employee max).
# Contient les informations professionnelles : poste, séniorité, solde congé...
# Référencé par crm.projects.project_manager_id et pm.tasks.assigned_employee_id.

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from app.database.connection import Base
from .enums import SeniorityEnum


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = {"schema": "hris"}

    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    team_id       = Column(Integer, ForeignKey("hris.teams.id"), nullable=False)

    # Manager hiérarchique direct (auto-référence sur la même table)
    manager_id    = Column(Integer, ForeignKey("hris.employees.id"), nullable=True)

    job_title     = Column(String, nullable=True)
    phone         = Column(String(20), nullable=True)
    seniority     = Column(
        SAEnum(SeniorityEnum, name="seniorityenum", schema="hris", native_enum=False),
        nullable=True,
    )
    hire_date     = Column(Date, nullable=True)
    leave_date    = Column(Date, nullable=True)   # NULL = encore en poste
    leave_balance = Column(Integer, default=22)
    created_at    = Column(DateTime, server_default=func.now())

    user    = relationship("User", back_populates="employee")
    team    = relationship("Team", back_populates="employees", foreign_keys=[team_id])
    manager = relationship(
        "Employee",
        foreign_keys=[manager_id],
        primaryjoin="Employee.manager_id == Employee.id",
        remote_side="Employee.id",
        uselist=False,
    )

    employee_skills     = relationship("EmployeeSkill",    back_populates="employee", cascade="all, delete-orphan")
    leaves              = relationship("Leave",            back_populates="employee", cascade="all, delete-orphan")
    leave_logs          = relationship("LeaveLog",         back_populates="employee", cascade="all, delete-orphan")
    calendar_events     = relationship("CalendarEvent",    back_populates="employee", cascade="all, delete-orphan")
    calendar_event_logs = relationship("CalendarEventLog", back_populates="employee", cascade="all, delete-orphan")
