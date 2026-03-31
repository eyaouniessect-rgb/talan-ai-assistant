# Modèle SQLAlchemy pour la table `users`.
# Champs : id, name, email, hashed_password, role (consultant|pm), created_at, is_active
# database/models/user.py
# database/models/user.py

from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
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