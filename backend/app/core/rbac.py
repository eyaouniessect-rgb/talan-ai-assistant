# app/core/rbac.py
# ═══════════════════════════════════════════════════════════
# RBAC par TOOL — vérifie les permissions avant chaque appel d'outil.
# Utilisé par les agents (CalendarAgent, RHAgent, etc.) pour
# vérifier si le rôle de l'utilisateur a accès à un tool donné.
# ═══════════════════════════════════════════════════════════
from sqlalchemy import select
from app.database.connection import AsyncSessionLocal
from app.database.models.public.permission import Permission


async def check_tool_permission(role: str, tool_name: str) -> bool:
    """
    Vérifie si un rôle a la permission d'utiliser un tool.
    Retourne True si autorisé, False sinon.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Permission).where(
                Permission.role == role,
                Permission.action == tool_name,
                Permission.allowed == True,
            )
        )
        return result.scalar_one_or_none() is not None


def tool_permission_denied_message(tool_name: str) -> str:
    """Message d'erreur quand un tool est refusé par RBAC."""
    return f"Accès refusé — vous n'avez pas la permission d'utiliser '{tool_name}'."
