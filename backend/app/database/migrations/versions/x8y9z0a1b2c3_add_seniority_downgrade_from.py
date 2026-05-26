"""add seniority_downgrade_from to staffing_assignments (idempotent)

Revision ID: x8y9z0a1b2c3
Revises: w7x8y9z0a1b2
Create Date: 2026-05-22

Sur certaines DB la colonne seniority_downgrade_from n'a jamais été créée
(migration u5v6w7x8y9z0 appliquée alors que la table existait déjà via un
autre chemin → CREATE TABLE silencieusement no-op). Cette migration ajoute
la colonne uniquement si elle manque. Idempotente : ne fait rien si déjà
présente.
"""
from alembic import op


revision      = 'x8y9z0a1b2c3'
down_revision = 'w7x8y9z0a1b2'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE project_management.staffing_assignments "
        "ADD COLUMN IF NOT EXISTS seniority_downgrade_from VARCHAR(20) NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE project_management.staffing_assignments "
        "DROP COLUMN IF EXISTS seniority_downgrade_from"
    )
