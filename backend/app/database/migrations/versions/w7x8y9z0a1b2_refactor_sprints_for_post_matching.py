"""refactor sprints table for post-matching flow

Revision ID: w7x8y9z0a1b2
Revises: v6w7x8y9z0a1
Create Date: 2026-05-14

Refactor de la table project_management.sprints pour supporter le flow
post-matching (persistance + sync Jira) :

  - DROP  : capacity_hours (obsolète — unité réelle = Story Points)
  - ADD   : sprint_number       (numéro 1, 2, 3 ...)
  - ADD   : target_capacity_sp  (capacité cible PM en SP)
  - ADD   : actual_sp           (SP réellement assignés)
  - ADD   : status              (planned | active | completed)
  - ADD   : jira_sprint_id      (ID Sprint Jira après sync)
  - ADD   : updated_at
  - ALTER : start_date, end_date → NOT NULL
  - INDEX : (project_id, sprint_number) UNIQUE

Nettoyage data : delete des lignes pipeline_state avec phase PHASE_7_SPRINT_PLANNING
(la phase sprints séparée a été fusionnée dans la phase staffing).
"""
from alembic import op
import sqlalchemy as sa


revision      = 'w7x8y9z0a1b2'
down_revision = 'v6w7x8y9z0a1'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── 1. Vider la table sprints (les anciennes données n'ont pas les nouveaux champs requis)
    op.execute("DELETE FROM project_management.sprints")

    # ── 2. Drop colonne obsolète
    op.drop_column("sprints", "capacity_hours", schema="project_management")

    # ── 3. Ajouter les nouveaux champs
    op.add_column(
        "sprints",
        sa.Column("sprint_number", sa.Integer(), nullable=False),
        schema="project_management",
    )
    op.add_column(
        "sprints",
        sa.Column("target_capacity_sp", sa.Integer(), nullable=False),
        schema="project_management",
    )
    op.add_column(
        "sprints",
        sa.Column("actual_sp", sa.Integer(), nullable=False, server_default="0"),
        schema="project_management",
    )
    op.add_column(
        "sprints",
        sa.Column("status", sa.String(), nullable=False, server_default="planned"),
        schema="project_management",
    )
    op.add_column(
        "sprints",
        sa.Column("jira_sprint_id", sa.Integer(), nullable=True),
        schema="project_management",
    )
    op.add_column(
        "sprints",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        schema="project_management",
    )

    # ── 4. Dates NOT NULL (étaient nullable, mais on en a toujours en sortie de staffing)
    op.alter_column("sprints", "start_date", nullable=False, schema="project_management")
    op.alter_column("sprints", "end_date",   nullable=False, schema="project_management")

    # ── 5. Index UNIQUE (project_id, sprint_number)
    op.create_unique_constraint(
        "uq_sprints_project_sprint_number",
        "sprints",
        ["project_id", "sprint_number"],
        schema="project_management",
    )

    # ── 6. Nettoyer pipeline_state des lignes phase=PHASE_7_SPRINT_PLANNING
    #     (cette phase a été fusionnée dans la phase staffing)
    op.execute(
        "DELETE FROM project_management.pipeline_state "
        "WHERE phase = 'PHASE_7_SPRINT_PLANNING'"
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_sprints_project_sprint_number",
        "sprints",
        schema="project_management",
    )
    op.alter_column("sprints", "start_date", nullable=True, schema="project_management")
    op.alter_column("sprints", "end_date",   nullable=True, schema="project_management")
    op.drop_column("sprints", "updated_at",         schema="project_management")
    op.drop_column("sprints", "jira_sprint_id",     schema="project_management")
    op.drop_column("sprints", "status",             schema="project_management")
    op.drop_column("sprints", "actual_sp",          schema="project_management")
    op.drop_column("sprints", "target_capacity_sp", schema="project_management")
    op.drop_column("sprints", "sprint_number",      schema="project_management")
    op.add_column(
        "sprints",
        sa.Column("capacity_hours", sa.Float(), nullable=True),
        schema="project_management",
    )
