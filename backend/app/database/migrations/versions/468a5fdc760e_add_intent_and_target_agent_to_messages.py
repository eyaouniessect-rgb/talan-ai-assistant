"""add intent and target_agent to messages

Revision ID: 468a5fdc760e
Revises: 6c41c4df82a4
Create Date: 2026-03-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '468a5fdc760e'
down_revision: Union[str, None] = '6c41c4df82a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ajoute uniquement les 2 nouvelles colonnes
    op.add_column('messages', sa.Column('intent', sa.String(), nullable=True))
    op.add_column('messages', sa.Column('target_agent', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'target_agent')
    op.drop_column('messages', 'intent')