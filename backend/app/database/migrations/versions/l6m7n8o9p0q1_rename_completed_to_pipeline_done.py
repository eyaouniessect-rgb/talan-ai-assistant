"""Renommer project status 'completed' → 'pipeline_done' et ajouter in_development/delivered

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-04-21

Le statut 'completed' était ambigu (fin du pipeline ou fin du projet ?).
On distingue maintenant :
  pipeline_done  → 12/12 phases IA validées
  in_development → développement en cours
  delivered      → projet livré
"""

from alembic import op


revision      = "l6m7n8o9p0q1"
down_revision = "k5l6m7n8o9p0"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        UPDATE crm.projects
        SET status = 'pipeline_done'
        WHERE status = 'completed'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE crm.projects
        SET status = 'completed'
        WHERE status IN ('pipeline_done', 'in_development', 'delivered')
    """)
