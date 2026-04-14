"""add steps column to messages

Revision ID: i3j4k5l6m7n8
Revises: f5a6b7c8d9e0
Create Date: 2026-04-12

Ajoute la colonne steps (JSONB) à public.messages.
Stocke les étapes de traitement réelles de l'agent pour chaque message assistant
(step_id, status, text, agent) — permet de les restaurer à l'affichage.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision      = "i3j4k5l6m7n8"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("steps", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "steps")
