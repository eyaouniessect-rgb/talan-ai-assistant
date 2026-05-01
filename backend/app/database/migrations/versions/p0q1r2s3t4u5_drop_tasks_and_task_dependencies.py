"""drop tasks and task_dependencies tables

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'p0q1r2s3t4u5'
down_revision = 'o9p0q1r2s3t4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop task_dependencies first (FK on tasks)
    op.drop_table('task_dependencies', schema='project_management')
    op.drop_table('tasks', schema='project_management')

    # Drop task-related enums
    op.execute("DROP TYPE IF EXISTS project_management.taskstatusenum")
    op.execute("DROP TYPE IF EXISTS project_management.tasktypeenum")


def downgrade() -> None:
    op.execute("""
        CREATE TYPE project_management.tasktypeenum AS ENUM (
            'DEVELOPMENT', 'TESTING', 'DESIGN', 'DOCUMENTATION', 'REVIEW', 'OTHER'
        )
    """)
    op.execute("""
        CREATE TYPE project_management.taskstatusenum AS ENUM (
            'TODO', 'IN_PROGRESS', 'DONE', 'BLOCKED'
        )
    """)

    op.create_table(
        'tasks',
        sa.Column('id',            sa.Integer(),    nullable=False),
        sa.Column('user_story_id', sa.Integer(),    nullable=False),
        sa.Column('sprint_id',     sa.Integer(),    nullable=True),
        sa.Column('title',         sa.String(255),  nullable=False),
        sa.Column('description',   sa.Text(),       nullable=True),
        sa.Column('task_type',     postgresql.ENUM(
            'DEVELOPMENT', 'TESTING', 'DESIGN', 'DOCUMENTATION', 'REVIEW', 'OTHER',
            name='tasktypeenum', schema='project_management', create_type=False
        ), nullable=True),
        sa.Column('status',        postgresql.ENUM(
            'TODO', 'IN_PROGRESS', 'DONE', 'BLOCKED',
            name='taskstatusenum', schema='project_management', create_type=False
        ), nullable=True),
        sa.Column('estimated_hours', sa.Float(),    nullable=True),
        sa.Column('assignee_id',   sa.Integer(),    nullable=True),
        sa.Column('jira_task_key', sa.String(50),   nullable=True),
        sa.Column('created_at',    sa.DateTime(),   nullable=True),
        sa.Column('updated_at',    sa.DateTime(),   nullable=True),
        sa.ForeignKeyConstraint(['user_story_id'], ['project_management.user_stories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sprint_id'],     ['project_management.sprints.id'],      ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assignee_id'],   ['hris.employees.id'],                  ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='project_management',
    )

    op.create_table(
        'task_dependencies',
        sa.Column('id',            sa.Integer(), nullable=False),
        sa.Column('task_id',       sa.Integer(), nullable=False),
        sa.Column('depends_on_id', sa.Integer(), nullable=False),
        sa.Column('created_at',    sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'],       ['project_management.tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['depends_on_id'], ['project_management.tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='project_management',
    )
