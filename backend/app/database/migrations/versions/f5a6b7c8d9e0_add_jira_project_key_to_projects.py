"""add jira_project_key to crm.projects

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-12

Ajoute la colonne jira_project_key (VARCHAR, nullable) à crm.projects.
Chaque projet PM stocke sa propre clé Jira — plus de clé globale partagée via .env.
"""

from alembic import op
import sqlalchemy as sa

revision      = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("jira_project_key", sa.String(), nullable=True),
        schema="crm",
    )


def downgrade() -> None:
    op.drop_column("projects", "jira_project_key", schema="crm")
