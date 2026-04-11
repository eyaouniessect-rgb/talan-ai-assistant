# orchestrator/utils/google_auth.py
#
# Utilitaire de vérification du token Google OAuth pour l'agent Calendar.
#
# Fonction :
#   - _check_google_token : vérifie qu'un token Google Calendar valide
#     existe en base pour un utilisateur avant d'appeler l'agent Calendar.
#
# Utilisée dans node3_executor.py (guard avant appel agent "calendar").

from __future__ import annotations


# ─────────────────────────────────────────────
# Vérification du token Google Calendar
# ─────────────────────────────────────────────

async def _check_google_token(user_id: int) -> tuple[bool, str]:
    """
    Vérifie que l'utilisateur a un token Google Calendar valide en base.
    Retourne (ok: bool, raison: str).

    Cas possibles :
      - ok=True,  raison="ok"               → token présent avec refresh_token
      - ok=False, raison="not_connected"    → aucun token trouvé en base
      - ok=False, raison="no_refresh_token" → token présent mais révoqué
      - ok=True,  raison="db_error"         → erreur DB, on laisse passer
        (l'agent Calendar renverra son propre message d'erreur si besoin)

    Note : l'expiration de access_token ne bloque PAS ici, car le refresh_token
    reste valide même après expiration — Google invalide le refresh_token
    uniquement en cas de révocation explicite.
    """
    try:
        from sqlalchemy import select
        from app.database.connection import AsyncSessionLocal
        from app.database.models.public.google_oauth_token import GoogleOAuthToken

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
            )
            token = result.scalar_one_or_none()

        if token is None:
            return False, "not_connected"
        if not token.refresh_token:
            return False, "no_refresh_token"

        return True, "ok"

    except Exception as e:
        print(f"  _check_google_token erreur : {e}")
        # En cas d'erreur DB → on laisse passer (fail-open pour ne pas bloquer l'utilisateur)
        return True, "db_error"
