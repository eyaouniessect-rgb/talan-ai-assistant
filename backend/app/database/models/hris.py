# database/models/hris.py
# Tables :
# - teams              : équipes
# - employees          : profil RH lié à un user
# - leaves             : demandes de congé
# - leave_logs         : historique des actions congé
# - calendar_events    : événements Google Calendar créés via le chat
# - calendar_event_logs: historique des actions calendrier

from sqlalchemy import Column, Integer, String, Date, ForeignKey, DateTime, func, Text
from sqlalchemy.orm import relationship
from app.database.connection import Base


# ─────────────────────────────────────────────
# Team
# ─────────────────────────────────────────────

class Team(Base):
    __tablename__ = "teams"
    __table_args__ = {"schema": "hris"}

    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False)
    manager_id = Column(Integer, ForeignKey("users.id"))

    employees  = relationship("Employee", back_populates="team")


# ─────────────────────────────────────────────
# Employee
# ─────────────────────────────────────────────

class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = {"schema": "hris"}

    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    team_id       = Column(Integer, ForeignKey("hris.teams.id"), nullable=False)
    skills        = Column(String)
    leave_balance = Column(Integer, default=22)
    created_at    = Column(DateTime, server_default=func.now())

    user  = relationship("User", back_populates="employee")
    team  = relationship("Team", back_populates="employees")
    leaves = relationship("Leave", back_populates="employee", cascade="all, delete-orphan")
    leave_logs = relationship("LeaveLog", back_populates="employee", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="employee", cascade="all, delete-orphan")
    calendar_event_logs = relationship("CalendarEventLog", back_populates="employee", cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# Leave
# ─────────────────────────────────────────────

class Leave(Base):
    __tablename__ = "leaves"
    __table_args__ = {"schema": "hris"}

    id          = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("hris.employees.id"))
    start_date  = Column(Date, nullable=False)
    end_date    = Column(Date, nullable=False)
    days_count  = Column(Integer)
    status      = Column(String, default="pending")  # pending | approved | rejected
    created_at  = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="leaves")
    logs     = relationship("LeaveLog", back_populates="leave", cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# LeaveLog — historique des actions congé
# ─────────────────────────────────────────────

class LeaveLog(Base):
    __tablename__ = "leave_logs"
    __table_args__ = {"schema": "hris"}

    id          = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    leave_id    = Column(Integer, ForeignKey("hris.leaves.id"), nullable=True)
    action      = Column(String, nullable=False)  # requested | approved | rejected | cancelled
    description = Column(Text, nullable=False)
    created_at  = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="leave_logs")
    leave    = relationship("Leave", back_populates="logs")


# ─────────────────────────────────────────────
# CalendarEvent
# ─────────────────────────────────────────────

class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = {"schema": "hris"}

    id              = Column(Integer, primary_key=True)
    employee_id     = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    google_event_id = Column(String, nullable=True)
    title           = Column(String, nullable=False)
    start_datetime  = Column(DateTime, nullable=False)
    end_datetime    = Column(DateTime, nullable=False)
    location        = Column(String, nullable=True)
    attendees       = Column(Text, nullable=True)   # emails séparés par virgule
    meet_link       = Column(String, nullable=True)
    html_link       = Column(String, nullable=True)
    created_at      = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="calendar_events")
    logs     = relationship("CalendarEventLog", back_populates="event", cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# CalendarEventLog — historique des actions calendrier
# ─────────────────────────────────────────────

class CalendarEventLog(Base):
    __tablename__ = "calendar_event_logs"
    __table_args__ = {"schema": "hris"}

    id                = Column(Integer, primary_key=True)
    employee_id       = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    calendar_event_id = Column(Integer, ForeignKey("hris.calendar_events.id"), nullable=True)
    google_event_id   = Column(String, nullable=True)
    event_title       = Column(String, nullable=False)
    action            = Column(String, nullable=False)  # created | updated | updated_schedule | deleted
    description       = Column(Text, nullable=False)
    created_at        = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="calendar_event_logs")
    event    = relationship("CalendarEvent", back_populates="logs")
