# models/hris/leave.py
# Schéma PostgreSQL : hris
#
# Table : leaves
# Demandes de congé d'un employé.
# Le champ justification_url pointe vers une image uploadée (proof document).

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from app.database.connection import Base
from .enums import LeaveTypeEnum, LeaveStatusEnum


class Leave(Base):
    __tablename__ = "leaves"
    __table_args__ = {"schema": "hris"}

    id                = Column(Integer, primary_key=True)
    employee_id       = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    leave_type        = Column(
        SAEnum(LeaveTypeEnum, name="leavetypeenum", schema="hris", native_enum=False),
        nullable=False,
        default=LeaveTypeEnum.ANNUAL,
    )
    start_date        = Column(Date, nullable=False)
    end_date          = Column(Date, nullable=False)
    days_count        = Column(Integer)
    status            = Column(
        SAEnum(LeaveStatusEnum, name="leavestatusenum", schema="hris", native_enum=False),
        nullable=False,
        default=LeaveStatusEnum.PENDING,
    )
    justification_url = Column(String, nullable=True)   # URL de l'image justificatif
    created_at        = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="leaves")
    logs     = relationship("LeaveLog", back_populates="leave", cascade="all, delete-orphan")
