"""Création du schéma project_management + colonne project_manager_id sur crm.projects

Revision ID: g1h2i3j4k5l6
Revises: a2b3c4d5e6f7
Create Date: 2026-04-08

Changements :
  - crm.projects          : + project_manager_id (FK → hris.employees.id)
  - CREATE SCHEMA project_management
  - project_management.pipeline_state  : suivi human-in-the-loop par phase
  - project_management.epics           : grands blocs fonctionnels (Phase 2)
  - project_management.user_stories    : histoires utilisateur (Phase 3-4)
  - project_management.story_dependencies : graphe dépendances stories (Phase 5)
  - project_management.sprints         : itérations avec capacité heures (Phase 10)
  - project_management.tasks           : tâches atomiques avec champs CPM (Phase 7-9)
  - project_management.task_dependencies  : graphe dépendances tâches (Phase 8)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ── 1. project_manager_id sur crm.projects ────────────────
    # Le PM responsable d'un projet — FK vers hris.employees (cohérent avec assignments)
    op.add_column(
        'projects',
        sa.Column('project_manager_id', sa.Integer(), sa.ForeignKey('hris.employees.id'), nullable=True),
        schema='crm',
    )
    op.create_index('ix_projects_project_manager_id', 'projects', ['project_manager_id'], schema='crm')

    # ── 2. Création du schéma project_management ─────────────
    op.execute('CREATE SCHEMA IF NOT EXISTS project_management')

    # ── 3. project_management.pipeline_state ─────────────────
    # Trace l'état de chaque phase pour chaque projet (human-in-the-loop)
    op.create_table(
        'pipeline_state',
        sa.Column('id',           sa.Integer(), primary_key=True),
        sa.Column('project_id',   sa.Integer(), sa.ForeignKey('crm.projects.id'),    nullable=False),
        sa.Column('phase',        sa.String(),  nullable=False),
        sa.Column('status',       sa.String(),  nullable=False, server_default='pending_ai'),
        sa.Column('ai_output',    JSONB,        nullable=True),
        sa.Column('pm_comment',   sa.Text(),    nullable=True),
        sa.Column('validated_by', sa.Integer(), sa.ForeignKey('hris.employees.id'), nullable=True),
        sa.Column('validated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at',   sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at',   sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('project_id', 'phase', name='uq_pipeline_project_phase'),
        schema='project_management',
    )
    op.create_index('ix_pipeline_state_project_id', 'pipeline_state', ['project_id'], schema='project_management')

    # ── 4. project_management.epics ──────────────────────────
    # Grands blocs fonctionnels — générés Phase 2, validés par le PM
    op.create_table(
        'epics',
        sa.Column('id',            sa.Integer(), primary_key=True),
        sa.Column('project_id',    sa.Integer(), sa.ForeignKey('crm.projects.id'), nullable=False),
        sa.Column('title',         sa.String(),  nullable=False),
        sa.Column('description',   sa.Text(),    nullable=True),
        sa.Column('status',        sa.String(),  nullable=False, server_default='draft'),
        sa.Column('jira_epic_key', sa.String(),  nullable=True),
        sa.Column('ai_metadata',   JSONB,        nullable=True),
        sa.Column('created_at',    sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        schema='project_management',
    )
    op.create_index('ix_epics_project_id', 'epics', ['project_id'], schema='project_management')

    # ── 5. project_management.user_stories ───────────────────
    # Histoires utilisateur — générées Phase 3, raffinées Phase 4
    op.create_table(
        'user_stories',
        sa.Column('id',                  sa.Integer(), primary_key=True),
        sa.Column('epic_id',             sa.Integer(), sa.ForeignKey('project_management.epics.id'), nullable=False),
        sa.Column('title',               sa.String(),  nullable=False),
        sa.Column('description',         sa.Text(),    nullable=True),
        sa.Column('story_points',        sa.Integer(), nullable=True),
        sa.Column('priority',            sa.String(),  nullable=True),  # MoSCoW — Phase 6
        sa.Column('status',              sa.String(),  nullable=False, server_default='draft'),
        sa.Column('acceptance_criteria', sa.Text(),    nullable=True),
        sa.Column('splitting_strategy',  sa.String(),  nullable=True),
        sa.Column('jira_issue_key',      sa.String(),  nullable=True),
        sa.Column('ai_metadata',         JSONB,        nullable=True),
        sa.Column('created_at',          sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        schema='project_management',
    )
    op.create_index('ix_user_stories_epic_id', 'user_stories', ['epic_id'], schema='project_management')

    # ── 6. project_management.story_dependencies ─────────────
    # Graphe de dépendances entre stories — Phase 5
    op.create_table(
        'story_dependencies',
        sa.Column('story_id',            sa.Integer(), sa.ForeignKey('project_management.user_stories.id'), primary_key=True),
        sa.Column('depends_on_story_id', sa.Integer(), sa.ForeignKey('project_management.user_stories.id'), primary_key=True),
        sa.UniqueConstraint('story_id', 'depends_on_story_id', name='uq_story_dependency'),
        schema='project_management',
    )

    # ── 7. project_management.sprints ────────────────────────
    # Itérations de livraison — Phase 10
    op.create_table(
        'sprints',
        sa.Column('id',             sa.Integer(), primary_key=True),
        sa.Column('project_id',     sa.Integer(), sa.ForeignKey('crm.projects.id'), nullable=False),
        sa.Column('name',           sa.String(),  nullable=False),
        sa.Column('start_date',     sa.Date(),    nullable=True),
        sa.Column('end_date',       sa.Date(),    nullable=True),
        sa.Column('capacity_hours', sa.Float(),   nullable=True),  # heures dispo équipe
        sa.Column('created_at',     sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        schema='project_management',
    )
    op.create_index('ix_sprints_project_id', 'sprints', ['project_id'], schema='project_management')

    # ── 8. project_management.tasks ──────────────────────────
    # Unités atomiques d'exécution (1 tâche = 1 employé)
    # Champs CPM : earliest_start, latest_start, slack, is_critical — Phase 9
    op.create_table(
        'tasks',
        sa.Column('id',                   sa.Integer(), primary_key=True),
        sa.Column('user_story_id',        sa.Integer(), sa.ForeignKey('project_management.user_stories.id'), nullable=False),
        sa.Column('title',                sa.String(),  nullable=False),
        sa.Column('type',                 sa.String(),  nullable=True),
        sa.Column('estimated_hours',      sa.Float(),   nullable=True),
        sa.Column('status',               sa.String(),  nullable=False, server_default='todo'),
        sa.Column('assigned_employee_id', sa.Integer(), sa.ForeignKey('hris.employees.id'), nullable=True),
        sa.Column('sprint_id',            sa.Integer(), sa.ForeignKey('project_management.sprints.id'), nullable=True),
        sa.Column('earliest_start',       sa.Float(),   nullable=True),   # CPM — Phase 9
        sa.Column('latest_start',         sa.Float(),   nullable=True),   # CPM — Phase 9
        sa.Column('slack',                sa.Float(),   nullable=True),   # 0 = chemin critique
        sa.Column('is_critical',          sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('jira_task_key',        sa.String(),  nullable=True),
        sa.Column('ai_metadata',          JSONB,        nullable=True),
        sa.Column('created_at',           sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        schema='project_management',
    )
    op.create_index('ix_tasks_user_story_id',        'tasks', ['user_story_id'],        schema='project_management')
    op.create_index('ix_tasks_assigned_employee_id', 'tasks', ['assigned_employee_id'], schema='project_management')
    op.create_index('ix_tasks_sprint_id',            'tasks', ['sprint_id'],            schema='project_management')

    # ── 9. project_management.task_dependencies ──────────────
    # Graphe de dépendances entre tâches — Phase 8 (entrée du CPM Phase 9)
    op.create_table(
        'task_dependencies',
        sa.Column('task_id',            sa.Integer(), sa.ForeignKey('project_management.tasks.id'), primary_key=True),
        sa.Column('depends_on_task_id', sa.Integer(), sa.ForeignKey('project_management.tasks.id'), primary_key=True),
        sa.UniqueConstraint('task_id', 'depends_on_task_id', name='uq_task_dependency'),
        schema='project_management',
    )


def downgrade() -> None:

    # Suppression dans l'ordre inverse des FK

    op.drop_table('task_dependencies', schema='project_management')

    op.drop_index('ix_tasks_sprint_id',            table_name='tasks', schema='project_management')
    op.drop_index('ix_tasks_assigned_employee_id', table_name='tasks', schema='project_management')
    op.drop_index('ix_tasks_user_story_id',        table_name='tasks', schema='project_management')
    op.drop_table('tasks', schema='project_management')

    op.drop_index('ix_sprints_project_id', table_name='sprints', schema='project_management')
    op.drop_table('sprints', schema='project_management')

    op.drop_table('story_dependencies', schema='project_management')

    op.drop_index('ix_user_stories_epic_id', table_name='user_stories', schema='project_management')
    op.drop_table('user_stories', schema='project_management')

    op.drop_index('ix_epics_project_id', table_name='epics', schema='project_management')
    op.drop_table('epics', schema='project_management')

    op.drop_index('ix_pipeline_state_project_id', table_name='pipeline_state', schema='project_management')
    op.drop_table('pipeline_state', schema='project_management')

    op.execute('DROP SCHEMA IF EXISTS project_management')

    op.drop_index('ix_projects_project_manager_id', table_name='projects', schema='crm')
    op.drop_column('projects', 'project_manager_id', schema='crm')
