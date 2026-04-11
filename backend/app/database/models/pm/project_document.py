# models/pm/project_document.py
# Schéma PostgreSQL : project_management
#
# Table : project_documents
# Stocke les fichiers CDC (Cahier des Charges) uploadés pour un projet.
#
# Design :
#   - Un projet peut avoir plusieurs CDC (versionning, corrections)
#   - file_hash (SHA-256) permet la détection de doublons
#   - Le pipeline référence document_id → node_extraction lit file_path en base
#   - Séparation claire : stockage documentaire ≠ pipeline IA

from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class ProjectDocument(Base):
    __tablename__ = "project_documents"
    __table_args__ = {"schema": "project_management"}

    id          = Column(Integer, primary_key=True)

    # Projet auquel appartient ce document
    project_id  = Column(Integer, ForeignKey("crm.projects.id"), nullable=False)

    # Métadonnées du fichier
    file_name   = Column(String,     nullable=False)        # nom original (ex: CDC_v2.pdf)
    file_path   = Column(String,     nullable=False)        # path absolu sur le serveur
    file_hash   = Column(String(64), nullable=False)        # SHA-256 hex — détection doublons
    file_size   = Column(BigInteger, nullable=False)        # taille en octets
    mime_type   = Column(String,     nullable=True)         # application/pdf, etc.

    # Qui a uploadé ce document (employee_id du PM connecté)
    uploaded_by = Column(Integer, ForeignKey("hris.employees.id"), nullable=True)

    created_at  = Column(DateTime, server_default=func.now(), nullable=False)

    # Relations
    project   = relationship("Project",  foreign_keys=[project_id])
    uploader  = relationship("Employee", foreign_keys=[uploaded_by])
