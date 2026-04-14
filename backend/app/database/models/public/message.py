# models/public/message.py
# Schéma PostgreSQL : public (défaut)
#
# Table : messages
# Chaque ligne = un tour de conversation (role: user | assistant).
# intent et target_agent sont remplis par le node1_intent de l'orchestrateur.

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database.connection import Base


class Message(Base):
    __tablename__ = "messages"

    id              = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role            = Column(String)              # user | assistant
    content         = Column(Text)
    intent          = Column(String, nullable=True)        # intention détectée par l'orchestrateur
    target_agent    = Column(String, nullable=True)        # agent cible dispatché
    steps           = Column(JSONB, nullable=True)         # étapes de traitement [{step_id, status, text, agent}]
    timestamp       = Column(DateTime, server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")
