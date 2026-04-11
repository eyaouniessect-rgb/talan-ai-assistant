# models/hris/calendar_event_log.py
# Schéma PostgreSQL : hris
#
# Table : calendar_event_logs
# Historique des actions sur les événements Google Calendar.
# Actions possibles : created | updated | updated_schedule | deleted

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class CalendarEventLog(Base):
    __tablename__ = "calendar_event_logs"
    __table_args__ = {"schema": "hris"}

    id                = Column(Integer, primary_key=True)
    employee_id       = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    calendar_event_id = Column(Integer, ForeignKey("hris.calendar_events.id"), nullable=True)
    google_event_id   = Column(String, nullable=True)
    event_title       = Column(String, nullable=False)
    action            = Column(String, nullable=False)   # created | updated | updated_schedule | deleted
    description       = Column(Text, nullable=False)
    created_at        = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="calendar_event_logs")
    event    = relationship("CalendarEvent", back_populates="logs")
