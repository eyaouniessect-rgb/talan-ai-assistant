# Modèle SQLAlchemy pour la table `users`.
# Champs : id, name, email, hashed_password, role (consultant|pm), created_at, is_active
# database/models/user.py
# database/models/user.py

from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database.connection import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    email = Column(String, unique=True, nullable=False, index=True)

    password = Column(String, nullable=False)  # bcrypt hash

    role = Column(String, nullable=False)  # consultant | pm | rh

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, server_default=func.now())

    # ─────────────────────────
    # Relations
    # ─────────────────────────

    # chat conversations
    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # lien vers profil RH
    employee = relationship(
        "Employee",
        back_populates="user",
        uselist=False
    )

    # Google OAuth token
    google_oauth_token = relationship(
        "GoogleOAuthToken",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )


class GoogleOAuthToken(Base):
    """Stocke le refresh_token Google OAuth2 par utilisateur."""
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