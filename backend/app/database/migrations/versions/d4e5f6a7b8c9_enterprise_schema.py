"""enterprise schema — départements, types de congé, séniorité, champs RH

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-30

Changements :
  - hris.departments       : nouvelle table (enum DepartmentEnum)
  - hris.teams             : + department_id, manager_id → hris.employees.id
  - hris.employees         : + manager_id (self-ref), job_title, seniority, hire_date, leave_date
  - hris.leaves            : + leave_type (enum), justification_url ; status reste String
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Table hris.departments ─────────────────────────────
    op.create_table(
        'departments',
        sa.Column('id',   sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(),  nullable=False, unique=True),
        schema='hris',
    )

    # ── 2. hris.teams — ajout department_id ──────────────────
    op.add_column(
        'teams',
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('hris.departments.id'), nullable=True),
        schema='hris',
    )

    # ── 3. hris.teams — changer manager_id → hris.employees.id
    # L'ancienne FK pointait vers users.id (sans nom explicite → nom auto PostgreSQL)
    op.execute("ALTER TABLE hris.teams DROP CONSTRAINT IF EXISTS teams_manager_id_fkey")
    # La nouvelle FK est ajoutée APRÈS la création des employees (use_alter pattern)
    # Elle sera posée en step 6 après les colonnes employees

    # ── 4. hris.employees — nouvelles colonnes ────────────────
    op.add_column(
        'employees',
        sa.Column('manager_id', sa.Integer(), nullable=True),
        schema='hris',
    )
    op.add_column(
        'employees',
        sa.Column('job_title', sa.String(), nullable=True),
        schema='hris',
    )
    op.add_column(
        'employees',
        sa.Column('seniority', sa.String(), nullable=True),
        schema='hris',
    )
    op.add_column(
        'employees',
        sa.Column('hire_date', sa.Date(), nullable=True),
        schema='hris',
    )
    op.add_column(
        'employees',
        sa.Column('leave_date', sa.Date(), nullable=True),
        schema='hris',
    )

    # ── 5. FK employees.manager_id → hris.employees.id ───────
    op.create_foreign_key(
        'fk_employee_manager_id',
        'employees', 'employees',
        ['manager_id'], ['id'],
        source_schema='hris',
        referent_schema='hris',
    )

    # ── 6. FK teams.manager_id → hris.employees.id (use_alter)
    op.create_foreign_key(
        'fk_team_manager_id',
        'teams', 'employees',
        ['manager_id'], ['id'],
        source_schema='hris',
        referent_schema='hris',
    )

    # ── 7. hris.leaves — ajout leave_type + justification_url
    op.add_column(
        'leaves',
        sa.Column('leave_type', sa.String(), nullable=True, server_default='annual'),
        schema='hris',
    )
    op.add_column(
        'leaves',
        sa.Column('justification_url', sa.String(), nullable=True),
        schema='hris',
    )
    # Rend leave_type NOT NULL après avoir fixé la valeur par défaut sur les lignes existantes
    op.execute("UPDATE hris.leaves SET leave_type = 'annual' WHERE leave_type IS NULL")
    op.alter_column('leaves', 'leave_type', nullable=False, schema='hris')


def downgrade() -> None:
    # leaves
    op.drop_column('leaves', 'justification_url', schema='hris')
    op.drop_column('leaves', 'leave_type', schema='hris')

    # FK teams.manager_id → employees
    op.drop_constraint('fk_team_manager_id', 'teams', schema='hris', type_='foreignkey')
    # FK employees.manager_id → employees
    op.drop_constraint('fk_employee_manager_id', 'employees', schema='hris', type_='foreignkey')

    # employees — nouvelles colonnes
    op.drop_column('employees', 'leave_date',  schema='hris')
    op.drop_column('employees', 'hire_date',   schema='hris')
    op.drop_column('employees', 'seniority',   schema='hris')
    op.drop_column('employees', 'job_title',   schema='hris')
    op.drop_column('employees', 'manager_id',  schema='hris')

    # teams — rétablit l'ancienne FK users.id
    op.drop_column('teams', 'department_id', schema='hris')
    op.create_foreign_key(
        None,
        'teams', 'users',
        ['manager_id'], ['id'],
        source_schema='hris',
    )

    # departments
    op.drop_table('departments', schema='hris')
