# models/crm/client.py
# Schéma PostgreSQL : crm
#
# Table : clients
# Représente les clients de Talan (entreprises commanditaires des projets).

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = {"schema": "crm"}

    id            = Column(Integer, primary_key=True)
    name          = Column(String, nullable=False)
    industry      = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)

    projects = relationship("Project", back_populates="client", cascade="all, delete-orphan")
