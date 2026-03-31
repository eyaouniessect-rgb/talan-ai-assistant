"""skills normalisés + table assignments (remplace project_members)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-30

Changements :
  - hris.skills          : nouvelle table (compétences)
  - hris.employee_skills : table de liaison Employee ↔ Skill (N-N) avec niveau
  - hris.employees       : suppression colonne skills (String)
  - crm.projects         : + start_date, renomme deadline → end_date
  - crm.project_members  : remplacée par crm.assignments
                           (+ allocation_percent, start_date, end_date)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. hris.skills ───────────────────────────────────────
    op.create_table(
        'skills',
        sa.Column('id',   sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(),  nullable=False, unique=True),
        schema='hris',
    )

    # ── 2. hris.employee_skills ──────────────────────────────
    op.create_table(
        'employee_skills',
        sa.Column('id',          sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('hris.employees.id'), nullable=False),
        sa.Column('skill_id',    sa.Integer(), sa.ForeignKey('hris.skills.id'),    nullable=False),
        sa.Column('level',       sa.String(),  nullable=True),
        schema='hris',
    )
    op.create_index('ix_employee_skills_employee_id', 'employee_skills', ['employee_id'], schema='hris')
    op.create_index('ix_employee_skills_skill_id',    'employee_skills', ['skill_id'],    schema='hris')

    # ── 3. Supprimer hris.employees.skills (String) ──────────
    op.drop_column('employees', 'skills', schema='hris')

    # ── 4. crm.projects — start_date + renommer deadline → end_date
    op.add_column(
        'projects',
        sa.Column('start_date', sa.Date(), nullable=True),
        schema='crm',
    )
    op.alter_column('projects', 'deadline', new_column_name='end_date', schema='crm')

    # ── 5. crm.project_members → crm.assignments ─────────────
    # On drop et recrée (plus propre que d'ALTER TABLE renommer + ajouter colonnes)
    op.drop_table('project_members', schema='crm')

    op.create_table(
        'assignments',
        sa.Column('id',                 sa.Integer(), primary_key=True),
        sa.Column('project_id',         sa.Integer(), sa.ForeignKey('crm.projects.id'),   nullable=False),
        sa.Column('employee_id',        sa.Integer(), sa.ForeignKey('hris.employees.id'), nullable=False),
        sa.Column('role_in_project',    sa.String(),  nullable=True),
        sa.Column('allocation_percent', sa.Integer(), nullable=True, server_default='100'),
        sa.Column('start_date',         sa.Date(),    nullable=True),
        sa.Column('end_date',           sa.Date(),    nullable=True),
        sa.Column('joined_at',          sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        schema='crm',
    )
    op.create_index('ix_assignments_project_id',  'assignments', ['project_id'],  schema='crm')
    op.create_index('ix_assignments_employee_id', 'assignments', ['employee_id'], schema='crm')


def downgrade() -> None:
    # assignments → project_members
    op.drop_index('ix_assignments_employee_id', table_name='assignments', schema='crm')
    op.drop_index('ix_assignments_project_id',  table_name='assignments', schema='crm')
    op.drop_table('assignments', schema='crm')

    op.create_table(
        'project_members',
        sa.Column('id',              sa.Integer(), primary_key=True),
        sa.Column('project_id',      sa.Integer(), sa.ForeignKey('crm.projects.id'),   nullable=False),
        sa.Column('employee_id',     sa.Integer(), sa.ForeignKey('hris.employees.id'), nullable=False),
        sa.Column('role_in_project', sa.String(),  nullable=True),
        sa.Column('joined_at',       sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        schema='crm',
    )

    # projects — end_date → deadline, drop start_date
    op.alter_column('projects', 'end_date', new_column_name='deadline', schema='crm')
    op.drop_column('projects', 'start_date', schema='crm')

    # employees — remettre skills String
    op.add_column(
        'employees',
        sa.Column('skills', sa.String(), nullable=True),
        schema='hris',
    )

    # employee_skills + skills
    op.drop_index('ix_employee_skills_skill_id',    table_name='employee_skills', schema='hris')
    op.drop_index('ix_employee_skills_employee_id', table_name='employee_skills', schema='hris')
    op.drop_table('employee_skills', schema='hris')
    op.drop_table('skills', schema='hris')
