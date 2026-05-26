"""add progress_status to staffing_assignments

Revision ID: z0a1b2c3d4e5
Revises: y9z0a1b2c3d4
Create Date: 2026-05-23

Avancement du travail de la story par le consultant assigné :
  - to_do (par défaut)  : story créée, pas encore commencée
  - in_progress         : story en cours de développement
  - done                : story terminée

Marqué automatiquement à 'done' pour toutes les stories d'un sprint
lorsque ce sprint passe à 'completed' (POST .../sprints/{n}/close).

Utilisé par le dashboard consultant pour les compteurs de tickets
to_do / in_progress / done par projet.
"""
from alembic import op
import sqlalchemy as sa


revision      = 'z0a1b2c3d4e5'
down_revision = 'y9z0a1b2c3d4'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "staffing_assignments",
        sa.Column(
            "progress_status",
            sa.String(length=20),
            nullable=False,
            server_default="to_do",
        ),
        schema="project_management",
    )


def downgrade() -> None:
    op.drop_column(
        "staffing_assignments",
        "progress_status",
        schema="project_management",
    )
