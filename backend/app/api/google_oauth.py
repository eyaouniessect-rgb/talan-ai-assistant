# Routes Google OAuth2 Calendar.
# GET /auth/google/connect  → redirige vers Google consent page
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
from app.database.models.user import GoogleOAuthToken

router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
MCP_TOKEN_PATH       = os.getenv("MCP_TOKEN_PATH", "")

SCOPES = "https://www.googleapis.com/auth/calendar"


# ─────────────────────────────────────────
# Étape 1 : redirige vers Google
# ─────────────────────────────────────────
@router.get("/connect")
async def google_connect(token: str = Query(..., description="JWT access token")):
    """
    Redirige l'utilisateur vers la page de consentement Google.
    Le token JWT est passé en query param car c'est une redirection navigateur.
    """
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


# ─────────────────────────────────────────
# Étape 2 : callback Google → sauvegarde tokens
# ─────────────────────────────────────────
@router.get("/callback")
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Reçoit le code Google OAuth2, échange contre des tokens,
    sauvegarde en DB et dans le tokens.json du MCP server.
    """
    user_id = int(state)

    # Échange le code contre des tokens
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

    # Récupère l'email Google de l'utilisateur
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

    # Calcule l'expiration
    expires_at = datetime.utcnow().replace(microsecond=0)
    from datetime import timedelta
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Upsert en base de données
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

    # Sauvegarde dans le tokens.json du MCP server
    _save_to_mcp_tokens(user_id, tokens)

    # Redirige vers le frontend avec succès
    frontend_url = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")[0]
    return RedirectResponse(f"{frontend_url}?google_connected=true")


# ─────────────────────────────────────────
# Statut : le user a-t-il connecté Google ?
# ─────────────────────────────────────────
@router.get("/status")
async def google_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne le statut Google Calendar de l'utilisateur courant.
    - connected: False          → jamais connecté
    - connected: True           → token présent
    - token_expired: True       → access_token expiré (refresh_token toujours valide)
    - needs_reconnect: True     → refresh_token manquant (accès révoqué, doit reconnecter)
    """
    user_id = current_user["user_id"]
    result = await db.execute(
        select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
    )
    token = result.scalar_one_or_none()

    if not token:
        return {"connected": False, "token_expired": False, "needs_reconnect": False}

    # Refresh token absent → accès révoqué
    if not token.refresh_token:
        return {
            "connected": False,
            "token_expired": False,
            "needs_reconnect": True,
            "google_email": token.google_email,
        }

    # Vérifie si l'access_token est expiré (le refresh_token reste valable)
    token_expired = False
    if token.expires_at:
        token_expired = datetime.utcnow() > token.expires_at

    return {
        "connected": True,
        "token_expired": token_expired,
        "needs_reconnect": False,
        "google_email": token.google_email,
    }


# ─────────────────────────────────────────
# Helper : mise à jour du tokens.json MCP
# ─────────────────────────────────────────
def _save_to_mcp_tokens(user_id: int, google_tokens: dict) -> None:
    """
    Sauvegarde (ou met à jour) les tokens dans le fichier tokens.json du MCP server.
    Le MCP stocke les comptes sous forme { accountId: credentials }.
    """
    if not MCP_TOKEN_PATH:
        return

    # Charge les tokens existants
    existing: dict = {}
    if os.path.exists(MCP_TOKEN_PATH):
        try:
            with open(MCP_TOKEN_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Ajoute / met à jour l'entrée pour cet utilisateur
    account_key = str(user_id)
    existing[account_key] = {
        "access_token":  google_tokens.get("access_token", ""),
        "refresh_token": google_tokens.get("refresh_token", ""),
        "token_type":    google_tokens.get("token_type", "Bearer"),
        "expiry_date":   int(datetime.utcnow().timestamp() * 1000) + google_tokens.get("expires_in", 3600) * 1000,
        "scope":         google_tokens.get("scope", "https://www.googleapis.com/auth/calendar"),
    }

    os.makedirs(os.path.dirname(MCP_TOKEN_PATH), exist_ok=True)
    with open(MCP_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
