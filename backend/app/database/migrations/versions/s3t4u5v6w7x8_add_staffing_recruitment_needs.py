"""add_staffing_recruitment_needs

Revision ID: s3t4u5v6w7x8
Revises: r2s3t4u5v6w7
Create Date: 2026-05-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision      = 's3t4u5v6w7x8'
down_revision = 'r2s3t4u5v6w7'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "staffing_recruitment_needs",
        sa.Column("id",                   sa.Integer(),     nullable=False, primary_key=True),
        sa.Column("project_id",           sa.Integer(),     nullable=False),
        sa.Column("required_profile",     sa.String(255),   nullable=False),
        sa.Column("suggested_job_titles", JSONB(),          nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reason",               sa.Text(),        nullable=False, server_default=sa.text("''")),
        sa.Column("status",               sa.String(20),    nullable=False, server_default="open"),
        sa.Column("created_at",           sa.DateTime(),    server_default=sa.text("now()")),
        sa.Column("updated_at",           sa.DateTime(),    server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["crm.projects.id"], ondelete="CASCADE"
        ),
        schema="project_management",
    )
    op.create_index(
        "ix_staffing_recruitment_needs_project_id",
        "staffing_recruitment_needs",
        ["project_id"],
        schema="project_management",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_staffing_recruitment_needs_project_id",
        table_name="staffing_recruitment_needs",
        schema="project_management",
    )
    op.drop_table("staffing_recruitment_needs", schema="project_management")
