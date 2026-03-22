# agents/shared/auth_middleware.py
# ═══════════════════════════════════════════════════════════
# Middleware d'authentification inter-agents A2A
# ═══════════════════════════════════════════════════════════
#
# Vérifie un Bearer token sur les endpoints sensibles :
# - /.well-known/agent.json (AgentCard)
# - /.well-known/agent-card.json (AgentCard v2)
# - / (endpoint de tâches A2A)
#
# Les agents et l'orchestrateur partagent un secret commun
# via la variable d'environnement A2A_SECRET_TOKEN.
#
# Sans ce token → 401 Unauthorized
# Avec un mauvais token → 403 Forbidden

import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

# ── Endpoints protégés ─────────────────────────────────────
PROTECTED_PATHS = {
    "/.well-known/agent.json",
    "/.well-known/agent-card.json",
    "/",
}

# ── Token secret partagé ──────────────────────────────────
A2A_SECRET = os.getenv("A2A_SECRET_TOKEN", "")


class A2AAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware Starlette qui protège les endpoints A2A
    avec un Bearer token partagé.
    """

    async def dispatch(self, request: Request, call_next):
        # ── Vérifie si l'endpoint est protégé ──────────────
        if request.url.path not in PROTECTED_PATHS:
            return await call_next(request)

        # ── Si pas de secret configuré → pas de protection ─
        # (mode développement sans token)
        if not A2A_SECRET:
            return await call_next(request)

        # ── Vérifie le header Authorization ─────────────────
        auth_header = request.headers.get("Authorization", "")

        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Missing Authorization header. Use: Bearer <token>"
                }
            )

        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Invalid Authorization format. Use: Bearer <token>"
                }
            )

        token = auth_header[7:]  # retire "Bearer "

        if token != A2A_SECRET:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "forbidden",
                    "message": "Invalid A2A token."
                }
            )

        # ── Token valide → continue ────────────────────────
        return await call_next(request)