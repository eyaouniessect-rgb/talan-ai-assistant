# models/public/conversation.py
# Schéma PostgreSQL : public (défaut)
#
# Table : conversations
# Regroupe les messages d'un échange entre un user et l'assistant.
# Utilisé par le LangGraph Checkpointer pour la mémoire long-terme.

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    title      = Column(String, default="Nouvelle conversation")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    user     = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
