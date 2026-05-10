# models/pm/staffing_recruitment_need.py
# Table : staffing_recruitment_needs
# Stocke les besoins de recrutement identifiés lors de la phase Staffing.
# Créée/mise à jour quand le PM marque un profil comme "recruit" dans la normalisation.

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database.connection import Base


class StaffingRecruitmentNeed(Base):
    __tablename__  = "staffing_recruitment_needs"
    __table_args__ = {"schema": "project_management"}

    id                   = Column(Integer, primary_key=True, index=True)
    project_id           = Column(
        Integer,
        ForeignKey("crm.projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    required_profile     = Column(String(255), nullable=False)
    suggested_job_titles = Column(JSONB,  nullable=False, default=list)
    reason               = Column(Text,   nullable=False, default="")
    # open | cancelled | covered
    status               = Column(String(20), nullable=False, default="open")
    created_at           = Column(DateTime, server_default=func.now())
    updated_at           = Column(DateTime, server_default=func.now(), onupdate=func.now())
