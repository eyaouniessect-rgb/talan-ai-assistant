# models/public/validators.py
# Schéma PostgreSQL : public (défaut)
#
# Schémas Pydantic pour les tables du schéma public.
# Utilisés pour la validation des requêtes API et la sérialisation des réponses.
# Séparés des modèles SQLAlchemy pour garder une séparation claire ORM / API.

from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────
# User
# ─────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str   # consultant | pm | rh


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None


# ─────────────────────────────────────────────
# Auth / Token
# ─────────────────────────────────────────────

class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─────────────────────────────────────────────
# Conversation & Message
# ─────────────────────────────────────────────

class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageRequest(BaseModel):
    conversation_id: int
    content: str


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    intent: Optional[str] = None
    target_agent: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}
