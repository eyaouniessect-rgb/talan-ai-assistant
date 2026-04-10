# models/hris/team.py
# Schéma PostgreSQL : hris
#
# Table : teams
# Représente les équipes au sein d'un département.
# Dépendance circulaire résolue via use_alter=True sur manager_id :
#   Team.manager_id → hris.employees.id
#   Employee.team_id → hris.teams.id

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = {"schema": "hris"}

    id            = Column(Integer, primary_key=True)
    name          = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("hris.departments.id"), nullable=True)

    # use_alter=True casse la dépendance circulaire Team ↔ Employee
    manager_id    = Column(
        Integer,
        ForeignKey("hris.employees.id", use_alter=True, name="fk_team_manager_id"),
        nullable=True,
    )

    department = relationship("Department", back_populates="teams")
    employees  = relationship("Employee", back_populates="team", foreign_keys="[Employee.team_id]")
    manager    = relationship("Employee", foreign_keys=[manager_id], uselist=False)
