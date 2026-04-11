# api/auth/__init__.py
# Exporte les routers du sous-domaine auth.

from .login import router as login_router
from .google_oauth import router as google_oauth_router
