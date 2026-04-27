"""story_dependency add SAFe+PMBOK fields

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'o9p0q1r2s3t4'
down_revision = 'n8o9p0q1r2s3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("story_dependencies",
        sa.Column("dependency_type", sa.String(), nullable=False,
                  server_default="functional"),
        schema="project_management",
    )
    op.add_column("story_dependencies",
        sa.Column("relation_type", sa.String(), nullable=False,
                  server_default="FS"),
        schema="project_management",
    )
    op.add_column("story_dependencies",
        sa.Column("is_blocking", sa.Boolean(), nullable=False,
                  server_default="true"),
        schema="project_management",
    )
    op.add_column("story_dependencies",
        sa.Column("level", sa.String(), nullable=False,
                  server_default="intra_epic"),
        schema="project_management",
    )
    op.add_column("story_dependencies",
        sa.Column("reason", sa.String(), nullable=True),
        schema="project_management",
    )


def downgrade():
    for col in ["dependency_type", "relation_type", "is_blocking", "level", "reason"]:
        op.drop_column("story_dependencies", col, schema="project_management")
