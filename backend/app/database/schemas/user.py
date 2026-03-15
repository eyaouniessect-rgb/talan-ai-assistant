# Schémas Pydantic pour la validation des données utilisateur :
# UserCreate, UserLogin, UserResponse, TokenResponse
# app/database/schemas/user.py
from pydantic import BaseModel, EmailStr

class UserLogin(BaseModel):
    email: str
    password: str

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str  # consultant | pm

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse