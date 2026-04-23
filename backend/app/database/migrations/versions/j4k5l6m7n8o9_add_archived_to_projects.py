"""add archived and archive_reason to crm.projects

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-04-21

Ajoute archived (BOOLEAN, défaut FALSE) et archive_reason (VARCHAR nullable)
à crm.projects pour permettre l'archivage des projets sans suppression.
"""

from alembic import op
import sqlalchemy as sa

revision      = "j4k5l6m7n8o9"
down_revision = "i3j4k5l6m7n8"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="crm",
    )
    op.add_column(
        "projects",
        sa.Column("archive_reason", sa.String(), nullable=True),
        schema="crm",
    )


def downgrade() -> None:
    op.drop_column("projects", "archive_reason", schema="crm")
    op.drop_column("projects", "archived",       schema="crm")
