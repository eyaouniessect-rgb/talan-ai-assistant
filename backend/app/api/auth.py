# Routes d'authentification.
# POST /auth/login     → vérifie email+password → retourne JWT access + refresh token
# POST /auth/refresh   → renouvelle l'access token depuis le refresh token
# POST /auth/logout    → invalide le token côté serveur
# app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.connection import get_db
from app.database.models.user import User
from app.database.schemas.user import UserCreate, TokenResponse, UserResponse
from app.core.security import verify_password, hash_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Connexion utilisateur.
    Accepte form-data OAuth2 (Swagger) — username = email.
    Retourne un JWT token + infos utilisateur.
    """
    # Cherche l'utilisateur en base (username = email dans OAuth2)
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    # Vérifie email + password
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    # Crée le JWT token
    token = create_access_token(data={
        "sub": str(user.id),
        "role": user.role,
        "name": user.name,
    })

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
        )
    )

@router.post("/register", response_model=TokenResponse)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Inscription d'un nouvel utilisateur.
    """
    # Vérifie si l'email existe déjà
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    # Crée l'utilisateur
    user = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(data={
        "sub": str(user.id),
        "role": user.role,
        "name": user.name,
    })

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
        )
    )