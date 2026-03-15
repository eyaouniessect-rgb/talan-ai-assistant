# Modèles SQLAlchemy pour les tables de chat :
# - `conversations` : id, user_id, title, created_at, updated_at
# - `messages`      : id, conversation_id, role (user|assistant), content, timestamp
#   → Utilisé par le LangGraph Checkpointer pour la long-term memory
# database/models/chat.py
# database/models/chat.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    title = Column(String, default="Nouvelle conversation")

    created_at = Column(DateTime, server_default=func.now())

    updated_at = Column(DateTime, onupdate=func.now())

    # ─────────────────────────
    # Relations
    # ─────────────────────────

    user = relationship(
        "User",
        back_populates="conversations"
    )

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)

    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id"),
        nullable=False
    )

    role = Column(String)  # user | assistant

    content = Column(Text)

    timestamp = Column(DateTime, server_default=func.now())

    # ─────────────────────────
    # Relations
    # ─────────────────────────

    conversation = relationship(
        "Conversation",
        back_populates="messages"
    )