# models/hris/skill.py
# Schéma PostgreSQL : hris
#
# Table : skills
# Référentiel des compétences techniques disponibles (ex: Python, React, AWS).
# Utilisé par le Staffing Agent (Phase 11) pour matcher les tâches aux bons employés.

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = {"schema": "hris"}

    id   = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)   # ex: "Python", "React", "AWS"

    employee_skills = relationship("EmployeeSkill", back_populates="skill", cascade="all, delete-orphan")
