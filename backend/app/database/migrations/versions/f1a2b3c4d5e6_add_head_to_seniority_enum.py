"""add head to seniority enum

Revision ID: f1a2b3c4d5e6
Revises: 6e97ca99d2fb
Create Date: 2026-04-04

"""
from alembic import op

revision = 'f1a2b3c4d5e6'
down_revision = '6e97ca99d2fb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SeniorityEnum est stocké comme VARCHAR (pas un type PostgreSQL natif)
    # Aucune migration DDL nécessaire — la valeur 'head' est acceptée directement
    pass


def downgrade() -> None:
    # PostgreSQL ne supporte pas la suppression d'une valeur d'enum
    # Pour rétrograder : recréer le type sans 'head' (opération manuelle)
    pass
