# models/hris/employee_skill.py
# Schéma PostgreSQL : hris
#
# Table : employee_skills
# Table de liaison N-N entre employees et skills.
# Le champ level indique le niveau de maîtrise de la compétence.
# Utilisé par le Staffing Agent pour scorer les candidats à une tâche.

from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from app.database.connection import Base
from .enums import SkillLevelEnum


class EmployeeSkill(Base):
    __tablename__ = "employee_skills"
    __table_args__ = {"schema": "hris"}

    id          = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    skill_id    = Column(Integer, ForeignKey("hris.skills.id"), nullable=False)
    level       = Column(
        SAEnum(SkillLevelEnum, name="skilllevel", schema="hris", native_enum=False),
        nullable=True,
    )

    employee = relationship("Employee", back_populates="employee_skills")
    skill    = relationship("Skill", back_populates="employee_skills")
