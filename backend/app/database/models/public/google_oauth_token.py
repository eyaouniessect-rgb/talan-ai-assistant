# models/public/google_oauth_token.py
# Schéma PostgreSQL : public (défaut)
#
# Table : google_oauth_tokens
# Stocke le refresh_token Google OAuth2 par utilisateur.
# Utilisé par l'agent Calendar pour accéder à Google Calendar sans re-login.

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class GoogleOAuthToken(Base):
    __tablename__ = "google_oauth_tokens"

    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    google_email  = Column(String(255), nullable=True)   # email du compte Google connecté
    refresh_token = Column(Text, nullable=False)
    access_token  = Column(Text, nullable=True)
    expires_at    = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, server_default=func.now())
    updated_at    = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="google_oauth_token")
