# models/pm/pipeline_state.py
# Schéma PostgreSQL : project_management
#
# Table : pipeline_state
# Trace l'état de chaque phase du pipeline IA pour un projet donné.
# Clé du human-in-the-loop : une phase ne peut avancer que si status = validated.
# ai_output stocke le résultat brut de l'agent pour affichage dans le dashboard PM.

from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database.connection import Base
from .enums import PipelinePhaseEnum, PipelineStatusEnum


class PipelineState(Base):
    __tablename__ = "pipeline_state"
    __table_args__ = (
        # Un projet ne peut avoir qu'un seul état par phase
        UniqueConstraint("project_id", "phase", name="uq_pipeline_project_phase"),
        {"schema": "project_management"},
    )

    id           = Column(Integer, primary_key=True)
    project_id   = Column(Integer, ForeignKey("crm.projects.id"), nullable=False)
    phase        = Column(
        SAEnum(PipelinePhaseEnum, name="pipelinephaseenum",
               schema="project_management", native_enum=False),
        nullable=False,
    )
    status       = Column(
        SAEnum(PipelineStatusEnum, name="pipelinestatusenum",
               schema="project_management", native_enum=False),
        nullable=False,
        default=PipelineStatusEnum.PENDING_AI,
    )

    # Snapshot JSONB du résultat de l'agent pour cette phase
    # Affiché dans le dashboard PM avant validation/rejet
    ai_output    = Column(JSONB, nullable=True)

    # Commentaire optionnel du PM lors de la validation ou du rejet
    pm_comment   = Column(Text, nullable=True)

    # employee_id du PM qui a validé/rejeté (cohérent avec crm.projects.project_manager_id)
    validated_by = Column(Integer, ForeignKey("hris.employees.id"), nullable=True)
    validated_at = Column(DateTime, nullable=True)
    created_at   = Column(DateTime, server_default=func.now())
    updated_at   = Column(DateTime, server_default=func.now(), onupdate=func.now())

    project      = relationship("Project", foreign_keys=[project_id])
    validator    = relationship("Employee", foreign_keys=[validated_by])
