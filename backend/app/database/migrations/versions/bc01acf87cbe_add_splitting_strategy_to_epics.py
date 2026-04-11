"""add_splitting_strategy_to_epics

Revision ID: bc01acf87cbe
Revises: h2i3j4k5l6m7
Create Date: 2026-04-10

"""
from alembic import op
import sqlalchemy as sa

revision = 'bc01acf87cbe'
down_revision = 'h2i3j4k5l6m7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'epics',
        sa.Column('splitting_strategy', sa.String(), nullable=True, server_default='by_feature'),
        schema='project_management',
    )


def downgrade() -> None:
    op.drop_column('epics', 'splitting_strategy', schema='project_management')
