# Modèle SQLAlchemy pour la table `permissions`.
# Champs : id, role (consultant|pm), action (create_leave, get_all_projects, etc.), allowed (bool)
# Peuplée au démarrage via les migrations Alembic (données initiales dans seed_permissions.py).
# database/models/permissions.py
# Table RBAC — définit ce que chaque rôle peut faire
from sqlalchemy import Column, Integer, String, Boolean, UniqueConstraint
from app.database.connection import Base


class Permission(Base):
    __tablename__ = "permissions"

    __table_args__ = (
        UniqueConstraint("role", "action", name="unique_role_action"),
    )

    id = Column(Integer, primary_key=True)

    role = Column(String, nullable=False)  # consultant | pm

    action = Column(String, nullable=False)  # create_leave | get_all_projects

    allowed = Column(Boolean, default=True)
