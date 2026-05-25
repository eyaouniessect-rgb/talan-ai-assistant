"""add priority_score, rank, is_critical to user_stories

Revision ID: b3c4d5e6f7a8
Revises: z0a1b2c3d4e5
Create Date: 2026-05-24

Persistance des sorties de la Phase 5 (Prioritization) directement
sur user_stories au lieu de seulement dans pipeline_state.ai_output :
  - priority_score : score CPM/backpropagation (Float)
  - rank           : ordre final (1 = à faire en premier) — utilisé par
                     story_distribution et le dashboard consultant
  - is_critical    : story sur le chemin critique (slack ≈ 0)
"""
from alembic import op
import sqlalchemy as sa


revision      = 'b3c4d5e6f7a8'
down_revision = 'z0a1b2c3d4e5'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "user_stories",
        sa.Column("priority_score", sa.Float(), nullable=True),
        schema="project_management",
    )
    op.add_column(
        "user_stories",
        sa.Column("rank", sa.Integer(), nullable=True),
        schema="project_management",
    )
    op.add_column(
        "user_stories",
        sa.Column(
            "is_critical",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="project_management",
    )
    op.create_index(
        "ix_user_stories_rank",
        "user_stories",
        ["rank"],
        schema="project_management",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_stories_rank",
        table_name="user_stories",
        schema="project_management",
    )
    op.drop_column("user_stories", "is_critical",    schema="project_management")
    op.drop_column("user_stories", "rank",           schema="project_management")
    op.drop_column("user_stories", "priority_score", schema="project_management")
