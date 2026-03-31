# database/models/hris.py
# Tables :
# - departments        : départements Talan Tunisie
# - teams              : équipes
# - employees          : profil RH lié à un user
# - leaves             : demandes de congé (avec type enum + justificatif)
# - leave_logs         : historique des actions congé
# - calendar_events    : événements Google Calendar créés via le chat
# - calendar_event_logs: historique des actions calendrier

import enum
from sqlalchemy import Column, Integer, String, Date, ForeignKey, DateTime, func, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from app.database.connection import Base


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class DepartmentEnum(str, enum.Enum):
    INNOVATION_FACTORY = "innovation_factory"
    SALESFORCE         = "salesforce"
    DATA               = "data"
    DIGITAL_FACTORY    = "digital_factory"
    TESTING            = "testing"
    CLOUD              = "cloud"
    SERVICE_NOW        = "service_now"


class SkillLevelEnum(str, enum.Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"
    EXPERT       = "expert"


class SeniorityEnum(str, enum.Enum):
    JUNIOR    = "junior"
    MID       = "mid"
    SENIOR    = "senior"
    LEAD      = "lead"
    PRINCIPAL = "principal"


class LeaveTypeEnum(str, enum.Enum):
    ANNUAL      = "annual"       # Congé annuel
    MATERNITY   = "maternity"    # Congé maternité
    PATERNITY   = "paternity"    # Congé paternité
    BEREAVEMENT = "bereavement"  # Congé décès d'un proche
    UNPAID      = "unpaid"       # Congé sans solde
    SICK        = "sick"         # Congé maladie
    OTHER       = "other"        # Autre


class LeaveStatusEnum(str, enum.Enum):
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    CANCELLED = "cancelled"


# ─────────────────────────────────────────────
# Department
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# Team
# ─────────────────────────────────────────────

class Team(Base):
    __tablename__ = "teams"
    __table_args__ = {"schema": "hris"}

    id            = Column(Integer, primary_key=True)
    name          = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("hris.departments.id"), nullable=True)
    # use_alter=True casse la dépendance circulaire Team ↔ Employee
    # (Team.manager_id → Employee.id, Employee.team_id → Team.id)
    manager_id    = Column(
        Integer,
        ForeignKey("hris.employees.id", use_alter=True, name="fk_team_manager_id"),
        nullable=True,
    )

    department = relationship("Department", back_populates="teams")
    # foreign_keys explicite pour lever l'ambiguïté Team ↔ Employee
    employees  = relationship(
        "Employee",
        back_populates="team",
        foreign_keys="[Employee.team_id]",
    )
    manager = relationship(
        "Employee",
        foreign_keys=[manager_id],
        uselist=False,
    )


# ─────────────────────────────────────────────
# Employee
# ─────────────────────────────────────────────

class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = {"schema": "hris"}

    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    team_id       = Column(Integer, ForeignKey("hris.teams.id"), nullable=False)
    manager_id    = Column(Integer, ForeignKey("hris.employees.id"), nullable=True)  # manager hiérarchique
    job_title     = Column(String, nullable=True)
    seniority     = Column(
        SAEnum(SeniorityEnum, name="seniorityenum", schema="hris", native_enum=False),
        nullable=True,
    )
    hire_date     = Column(Date, nullable=True)    # date d'embauche
    leave_date    = Column(Date, nullable=True)    # date de départ (NULL = encore en poste)
    leave_balance = Column(Integer, default=22)
    created_at    = Column(DateTime, server_default=func.now())

    user  = relationship("User", back_populates="employee")
    team  = relationship("Team", back_populates="employees", foreign_keys=[team_id])
    # Relation vers le manager direct (auto-référence sur la même table)
    manager = relationship(
        "Employee",
        foreign_keys="[Employee.manager_id]",
        primaryjoin="Employee.manager_id == Employee.id",
        uselist=False,
    )

    employee_skills     = relationship("EmployeeSkill",    back_populates="employee", cascade="all, delete-orphan")
    leaves              = relationship("Leave",            back_populates="employee", cascade="all, delete-orphan")
    leave_logs          = relationship("LeaveLog",         back_populates="employee", cascade="all, delete-orphan")
    calendar_events     = relationship("CalendarEvent",    back_populates="employee", cascade="all, delete-orphan")
    calendar_event_logs = relationship("CalendarEventLog", back_populates="employee", cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# Leave
# ─────────────────────────────────────────────

class Leave(Base):
    __tablename__ = "leaves"
    __table_args__ = {"schema": "hris"}

    id                = Column(Integer, primary_key=True)
    employee_id       = Column(Integer, ForeignKey("hris.employees.id"))
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


# ─────────────────────────────────────────────
# Skill
# ─────────────────────────────────────────────

class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = {"schema": "hris"}

    id   = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)  # ex: "Python", "React", "AWS"

    employee_skills = relationship("EmployeeSkill", back_populates="skill", cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# EmployeeSkill — table de liaison N-N
# ─────────────────────────────────────────────

class EmployeeSkill(Base):
    __tablename__ = "employee_skills"
    __table_args__ = {"schema": "hris"}

    id          = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    skill_id    = Column(Integer, ForeignKey("hris.skills.id"),    nullable=False)
    level       = Column(
        SAEnum(SkillLevelEnum, name="skilllevel", schema="hris", native_enum=False),
        nullable=True,
    )

    employee = relationship("Employee", back_populates="employee_skills")
    skill    = relationship("Skill",    back_populates="employee_skills")
