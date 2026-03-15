# Node 2 — Vérification des permissions (déterministe, sans LLM).
# Interroge la table PERMISSIONS en base avec (role, intention).
# Si autorisé  → passe à Node 3
# Si refusé    → retourne immédiatement une réponse "bloqué" au frontend
# C'est la couche de sécurité métier principale de l'architecture.
from sqlalchemy import select
from app.orchestrator.state import AssistantState
from app.database.models.permissions import Permission
from app.database.connection import AsyncSessionLocal

async def node2_check_permission(state: AssistantState) -> AssistantState:
    """
    Node 2 — Vérifie si le rôle de l'utilisateur
    est autorisé à effectuer l'intention détectée.
    Consulte la table `permissions` en base (RBAC).
    Pas de LLM ici — logique purement déterministe.
    """
    role   = state["role"]
    intent = state["intent"]

    # Intentions toujours autorisées (pas besoin de vérifier)
    if intent in ("unknown", "search_docs"):
        return {**state, "is_authorized": True}

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Permission).where(
                Permission.role == role,
                Permission.action == intent,
                Permission.allowed == True,
            )
        )
        permission = result.scalar_one_or_none()

    return {**state, "is_authorized": permission is not None}