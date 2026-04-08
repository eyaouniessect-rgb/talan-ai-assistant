"""add phone to employees

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = 'a2b3c4d5e6f7'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'employees',
        sa.Column('phone', sa.String(20), nullable=True),
        schema='hris',
    )


def downgrade() -> None:
    op.drop_column('employees', 'phone', schema='hris')
