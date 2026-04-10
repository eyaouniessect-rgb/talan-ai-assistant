# models/public/permission.py
# Schéma PostgreSQL : public (défaut)
#
# Table : permissions
# Table RBAC — définit ce que chaque rôle peut faire.
# Peuplée au démarrage via scripts/seed_permissions.py.
# Contrainte unique sur (role, action) pour éviter les doublons.

from sqlalchemy import Column, Integer, String, Boolean, UniqueConstraint
from app.database.connection import Base


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("role", "action", name="unique_role_action"),
    )

    id      = Column(Integer, primary_key=True)
    role    = Column(String, nullable=False)    # consultant | pm | rh
    action  = Column(String, nullable=False)    # create_leave | get_all_projects | ...
    allowed = Column(Boolean, default=True)
