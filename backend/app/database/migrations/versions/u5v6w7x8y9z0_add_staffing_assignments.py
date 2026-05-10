"""add_staffing_assignments

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-05-10

Persiste les affectations Step 5 (Matching) du pipeline Staffing.
Une ligne = une affectation (story × required_profile × employee).
Une story multi-profils produit plusieurs lignes.

Permet :
  - Dashboard PM cross-projets (qui travaille sur quoi).
  - Audit / explainability (matched_skills, inferred, missing, score, reason).
  - Reprise rapide après validation finale du staffing.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision      = 'u5v6w7x8y9z0'
down_revision = 't4u5v6w7x8y9'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "staffing_assignments",
        sa.Column("id",                   sa.Integer(),     nullable=False, primary_key=True),
        sa.Column("project_id",           sa.Integer(),     nullable=False),
        sa.Column("sprint_number",        sa.Integer(),     nullable=False),
        sa.Column("story_id",             sa.Integer(),     nullable=False),
        sa.Column("story_title",          sa.Text(),        nullable=False, server_default=""),
        sa.Column("story_points",         sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("required_profile",     sa.String(255),   nullable=False),
        sa.Column("required_level",       sa.String(20),    nullable=False, server_default="MID"),
        sa.Column("required_skills",      JSONB(),          nullable=False, server_default=sa.text("'[]'::jsonb")),

        sa.Column("employee_id",          sa.Integer(),     nullable=True),
        sa.Column("employee_name",        sa.String(255),   nullable=True),
        sa.Column("employee_seniority",   sa.String(20),    nullable=True),
        sa.Column("job_title",            sa.String(255),   nullable=True),

        sa.Column("allocated_sp",         sa.Float(),       nullable=False, server_default="0"),
        sa.Column("skill_score",          sa.Float(),       nullable=True),
        sa.Column("match_level",          sa.String(20),    nullable=True),  # excellent|good|medium|weak

        sa.Column("matched_skills",       JSONB(),          nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("inferred_matches",     JSONB(),          nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("missing_skills",       JSONB(),          nullable=False, server_default=sa.text("'[]'::jsonb")),

        # assigned | assigned_with_warning | missing_profile | capacity_gap
        # | seniority_gap | no_available_candidate | manual_decision_required
        sa.Column("status",               sa.String(40),    nullable=False),
        sa.Column("warning_type",         sa.String(40),    nullable=True),
        # Si la séniorité a été dégradée (SENIOR → MID, MID → JUNIOR), niveau initialement requis.
        sa.Column("seniority_downgrade_from", sa.String(20), nullable=True),
        sa.Column("reason",               sa.Text(),        nullable=False, server_default=""),

        # Stockée en JSON pour les manual_decision_required (liste de CandidateOption).
        sa.Column("candidate_options",    JSONB(),          nullable=False, server_default=sa.text("'[]'::jsonb")),

        sa.Column("created_at",           sa.DateTime(),    server_default=sa.text("now()")),
        sa.Column("updated_at",           sa.DateTime(),    server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(["project_id"], ["crm.projects.id"],          ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["story_id"],   ["project_management.user_stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["hris.employees.id"],       ondelete="SET NULL"),
        schema="project_management",
    )

    op.create_index(
        "ix_staffing_assignments_project_id",
        "staffing_assignments", ["project_id"], schema="project_management",
    )
    op.create_index(
        "ix_staffing_assignments_employee_id",
        "staffing_assignments", ["employee_id"], schema="project_management",
    )
    op.create_index(
        "ix_staffing_assignments_story_id",
        "staffing_assignments", ["story_id"], schema="project_management",
    )
    op.create_index(
        "ix_staffing_assignments_project_sprint",
        "staffing_assignments", ["project_id", "sprint_number"],
        schema="project_management",
    )


def downgrade() -> None:
    for idx in (
        "ix_staffing_assignments_project_sprint",
        "ix_staffing_assignments_story_id",
        "ix_staffing_assignments_employee_id",
        "ix_staffing_assignments_project_id",
    ):
        op.drop_index(idx, table_name="staffing_assignments", schema="project_management")
    op.drop_table("staffing_assignments", schema="project_management")
