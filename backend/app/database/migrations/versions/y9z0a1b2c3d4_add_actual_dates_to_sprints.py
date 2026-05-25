"""add actual_start_date and actual_end_date to sprints

Revision ID: y9z0a1b2c3d4
Revises: x8y9z0a1b2c3
Create Date: 2026-05-22

Distinction date planifiée vs date réelle pour les sprints :
  - start_date / end_date    : dates planifiées (calculées au matching)
  - actual_start_date        : date réelle de démarrage (clic PM)
  - actual_end_date          : date réelle de clôture (clic PM)

La date réelle est celle envoyée à Jira et utilisée pour les burndowns,
historiques et reporting. La date planifiée sert seulement à détecter
les démarrages anticipés (warning UI).
"""
from alembic import op
import sqlalchemy as sa


revision      = 'y9z0a1b2c3d4'
down_revision = 'x8y9z0a1b2c3'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "sprints",
        sa.Column("actual_start_date", sa.Date(), nullable=True),
        schema="project_management",
    )
    op.add_column(
        "sprints",
        sa.Column("actual_end_date", sa.Date(), nullable=True),
        schema="project_management",
    )


def downgrade() -> None:
    op.drop_column("sprints", "actual_end_date",   schema="project_management")
    op.drop_column("sprints", "actual_start_date", schema="project_management")
