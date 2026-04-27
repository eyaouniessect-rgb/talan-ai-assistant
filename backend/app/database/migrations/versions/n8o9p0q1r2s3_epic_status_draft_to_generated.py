"""epic status draft -> generated

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-04-25
"""
from alembic import op

revision = 'n8o9p0q1r2s3'
down_revision = 'm7n8o9p0q1r2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE project_management.epics
        SET status = 'GENERATED'
        WHERE upper(status) = 'DRAFT'
    """)


def downgrade():
    op.execute("""
        UPDATE project_management.epics
        SET status = 'DRAFT'
        WHERE upper(status) = 'GENERATED'
    """)
