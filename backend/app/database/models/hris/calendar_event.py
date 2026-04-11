# models/hris/calendar_event.py
# Schéma PostgreSQL : hris
#
# Table : calendar_events
# Événements Google Calendar créés via l'agent Calendar.
# google_event_id est l'identifiant retourné par l'API Google Calendar.

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = {"schema": "hris"}

    id              = Column(Integer, primary_key=True)
    employee_id     = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    google_event_id = Column(String, nullable=True)    # ID retourné par Google Calendar API
    title           = Column(String, nullable=False)
    start_datetime  = Column(DateTime, nullable=False)
    end_datetime    = Column(DateTime, nullable=False)
    location        = Column(String, nullable=True)
    attendees       = Column(Text, nullable=True)      # emails séparés par virgule
    meet_link       = Column(String, nullable=True)
    html_link       = Column(String, nullable=True)
    created_at      = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="calendar_events")
    logs     = relationship("CalendarEventLog", back_populates="event", cascade="all, delete-orphan")
