# api/auth/google_oauth.py
# Schéma : public
#
# Routes Google OAuth2 pour la connexion Google Calendar.
# GET /auth/google/connect  → redirige vers la page de consentement Google
# GET /auth/google/callback → reçoit le code, échange les tokens, sauvegarde en DB + tokens.json MCP
# GET /auth/google/status   → vérifie si l'utilisateur a déjà connecté son Google Calendar

import json
import os
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, decode_token
from app.database.connection import get_db
from app.database.models.public.google_oauth_token import GoogleOAuthToken

router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
MCP_TOKEN_PATH       = os.getenv("MCP_TOKEN_PATH", "")

SCOPES = "https://www.googleapis.com/auth/calendar"


@router.get("/connect")
async def google_connect(token: str = Query(..., description="JWT access token")):
    """Redirige l'utilisateur vers la page de consentement Google."""
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        "&response_type=code"
        f"&scope={SCOPES}"
        "&access_type=offline"
        "&prompt=consent"
        f"&state={user_id}"
    )
    return RedirectResponse(url)


@router.get("/callback")
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Reçoit le code Google OAuth2, échange contre des tokens, sauvegarde en DB et MCP."""
    user_id = int(state)

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Google token exchange failed: {token_resp.text}")
        tokens = token_resp.json()

    access_token  = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in    = tokens.get("expires_in", 3600)

    if not refresh_token:
        raise HTTPException(status_code=400, detail="Aucun refresh_token reçu. Assurez-vous d'avoir révoqué l'accès précédent.")

    google_email = None
    try:
        async with httpx.AsyncClient() as client:
            userinfo = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo.status_code == 200:
                google_email = userinfo.json().get("email")
    except Exception:
        pass

    from datetime import timedelta
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    result = await db.execute(
        select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.access_token  = access_token
        existing.refresh_token = refresh_token
        existing.expires_at    = expires_at
        existing.google_email  = google_email
        existing.updated_at    = datetime.utcnow()
    else:
        db.add(GoogleOAuthToken(
            user_id       = user_id,
            google_email  = google_email,
            refresh_token = refresh_token,
            access_token  = access_token,
            expires_at    = expires_at,
        ))
    await db.commit()

    _save_to_mcp_tokens(user_id, tokens)

    frontend_url = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")[0]
    return RedirectResponse(f"{frontend_url}?google_connected=true")


@router.get("/status")
async def google_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne le statut de connexion Google Calendar de l'utilisateur courant."""
    user_id = current_user["user_id"]
    result = await db.execute(
        select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
    )
    token = result.scalar_one_or_none()

    if not token:
        return {"connected": False, "token_expired": False, "needs_reconnect": False}

    if not token.refresh_token:
        return {
            "connected": False,
            "token_expired": False,
            "needs_reconnect": True,
            "google_email": token.google_email,
        }

    token_expired = False
    if token.expires_at:
        token_expired = datetime.utcnow() > token.expires_at

    return {
        "connected": True,
        "token_expired": token_expired,
        "needs_reconnect": False,
        "google_email": token.google_email,
    }


def _save_to_mcp_tokens(user_id: int, google_tokens: dict) -> None:
    """Sauvegarde les tokens dans le fichier tokens.json du MCP server."""
    if not MCP_TOKEN_PATH:
        return

    existing: dict = {}
    if os.path.exists(MCP_TOKEN_PATH):
        try:
            with open(MCP_TOKEN_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing[str(user_id)] = {
        "access_token":  google_tokens.get("access_token", ""),
        "refresh_token": google_tokens.get("refresh_token", ""),
        "token_type":    google_tokens.get("token_type", "Bearer"),
        "expiry_date":   int(datetime.utcnow().timestamp() * 1000) + google_tokens.get("expires_in", 3600) * 1000,
        "scope":         google_tokens.get("scope", "https://www.googleapis.com/auth/calendar"),
    }

    os.makedirs(os.path.dirname(MCP_TOKEN_PATH), exist_ok=True)
    with open(MCP_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
