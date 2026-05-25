"""drop candidate_options from staffing_assignments

Revision ID: v6w7x8y9z0a1
Revises: u5v6w7x8y9z0
Create Date: 2026-05-13

La colonne candidate_options était utilisée pour le statut
manual_decision_required. Depuis que le tie-break final se fait
sur employee_id, ce statut n'est plus produit — la colonne est devenue
toujours vide et peut être supprimée.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision      = 'v6w7x8y9z0a1'
down_revision = 'u5v6w7x8y9z0'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.drop_column(
        "staffing_assignments",
        "candidate_options",
        schema="project_management",
    )


def downgrade() -> None:
    op.add_column(
        "staffing_assignments",
        sa.Column(
            "candidate_options",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="project_management",
    )
