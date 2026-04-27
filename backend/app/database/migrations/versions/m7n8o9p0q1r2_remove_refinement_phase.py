"""remove refinement phase — StoryStatus draft/refined → generated

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'm7n8o9p0q1r2'
down_revision = 'l6m7n8o9p0q1'
branch_labels = None
depends_on = None


def upgrade():
    # Migrer les valeurs existantes : "draft" et "refined" → "generated"
    op.execute("""
        UPDATE project_management.user_stories
        SET status = 'generated'
        WHERE status IN ('draft', 'refined')
    """)

    # Supprimer pipeline_state des phases de raffinement si elles existent
    op.execute("""
        DELETE FROM project_management.pipeline_state
        WHERE phase = 'phase_4_refinement'
    """)


def downgrade():
    # Remettre "generated" → "draft" (approximatif)
    op.execute("""
        UPDATE project_management.user_stories
        SET status = 'draft'
        WHERE status = 'generated'
    """)
