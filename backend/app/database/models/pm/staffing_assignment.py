# models/pm/staffing_assignment.py
# Table : staffing_assignments
# Stocke les affectations Step 5 (Matching) du pipeline Staffing.
# Une ligne = une affectation (story × required_profile × employee).

from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database.connection import Base


class StaffingAssignment(Base):
    __tablename__  = "staffing_assignments"
    __table_args__ = {"schema": "project_management"}

    id = Column(Integer, primary_key=True, index=True)

    project_id = Column(
        Integer,
        ForeignKey("crm.projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sprint_number = Column(Integer, nullable=False)

    story_id = Column(
        Integer,
        ForeignKey("project_management.user_stories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    story_title    = Column(Text,    nullable=False, default="")
    story_points   = Column(Integer, nullable=False, default=0)

    required_profile = Column(String(255), nullable=False)
    required_level   = Column(String(20),  nullable=False, default="MID")
    required_skills  = Column(JSONB,       nullable=False, default=list)

    employee_id = Column(
        Integer,
        ForeignKey("hris.employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    employee_name      = Column(String(255), nullable=True)
    employee_seniority = Column(String(20),  nullable=True)
    job_title          = Column(String(255), nullable=True)

    allocated_sp = Column(Float,       nullable=False, default=0.0)
    skill_score  = Column(Float,       nullable=True)
    match_level  = Column(String(20),  nullable=True)   # excellent|good|medium|weak

    matched_skills   = Column(JSONB, nullable=False, default=list)
    inferred_matches = Column(JSONB, nullable=False, default=list)
    missing_skills   = Column(JSONB, nullable=False, default=list)

    # assigned | assigned_with_warning | missing_profile | capacity_gap
    # | seniority_gap | no_available_candidate | manual_decision_required
    status       = Column(String(40), nullable=False)
    warning_type = Column(String(40), nullable=True)
    # Si la séniorité a été dégradée pour ne pas bloquer le matching.
    seniority_downgrade_from = Column(String(20), nullable=True)
    reason       = Column(Text,       nullable=False, default="")

    # Pour manual_decision_required : liste sérialisée de CandidateOption.
    candidate_options = Column(JSONB, nullable=False, default=list)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
