"""add leave_balance to employees

Revision ID: bfefc89e9956
Revises: 468a5fdc760e
Create Date: 2026-03-17

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'bfefc89e9956'
down_revision: Union[str, None] = '468a5fdc760e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'employees',
        sa.Column('leave_balance', sa.Integer(), nullable=True),
        schema='hris'
    )


def downgrade() -> None:
    op.drop_column('employees', 'leave_balance', schema='hris')