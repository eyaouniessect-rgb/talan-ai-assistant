# models/hris/leave_log.py
# Schéma PostgreSQL : hris
#
# Table : leave_logs
# Historique de toutes les actions sur une demande de congé.
# Actions possibles : requested | approved | rejected | cancelled

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class LeaveLog(Base):
    __tablename__ = "leave_logs"
    __table_args__ = {"schema": "hris"}

    id          = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    leave_id    = Column(Integer, ForeignKey("hris.leaves.id"), nullable=True)
    action      = Column(String, nullable=False)    # requested | approved | rejected | cancelled
    description = Column(Text, nullable=False)
    created_at  = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="leave_logs")
    leave    = relationship("Leave", back_populates="logs")
