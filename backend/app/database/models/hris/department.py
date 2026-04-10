# models/hris/department.py
# Schéma PostgreSQL : hris
#
# Table : departments
# Représente les départements de Talan Tunisie.
# Valeurs contraintes par DepartmentEnum.

from sqlalchemy import Column, Integer
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from app.database.connection import Base
from .enums import DepartmentEnum


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = {"schema": "hris"}

    id   = Column(Integer, primary_key=True)
    name = Column(
        SAEnum(DepartmentEnum, name="departmentenum", schema="hris", native_enum=False),
        nullable=False,
        unique=True,
    )

    teams = relationship("Team", back_populates="department")
