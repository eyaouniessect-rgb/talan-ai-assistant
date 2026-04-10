# models/public/user.py
# Schéma PostgreSQL : public (défaut)
#
# Table : users
# Représente le compte d'authentification d'un utilisateur.
# Rôles possibles : consultant | pm | rh
# Lié au profil RH via hris.employees.user_id

from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    email      = Column(String, unique=True, nullable=False, index=True)
    password   = Column(String, nullable=False)   # bcrypt hash
    role       = Column(String, nullable=False)   # consultant | pm | rh
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    # Historique des conversations chat
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")

    # Profil RH (1 user = 1 employee max)
    employee = relationship("Employee", back_populates="user", uselist=False)

    # Token Google OAuth2 pour l'agent Calendar
    google_oauth_token = relationship("GoogleOAuthToken", back_populates="user", uselist=False, cascade="all, delete-orphan")
