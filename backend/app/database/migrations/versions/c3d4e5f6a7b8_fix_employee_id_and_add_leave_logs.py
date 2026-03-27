"""fix calendar tables to use employee_id and add leave_logs

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-27

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Recrée calendar_event_logs avec employee_id ────
    op.drop_index('ix_calendar_event_logs_user_id', table_name='calendar_event_logs', schema='hris')
    op.drop_table('calendar_event_logs', schema='hris')

    # ── 2. Recrée calendar_events avec employee_id ────────
    op.drop_index('ix_calendar_events_start',   table_name='calendar_events', schema='hris')
    op.drop_index('ix_calendar_events_user_id', table_name='calendar_events', schema='hris')
    op.drop_table('calendar_events', schema='hris')

    op.create_table(
        'calendar_events',
        sa.Column('id',              sa.Integer(),  primary_key=True),
        sa.Column('employee_id',     sa.Integer(),  sa.ForeignKey('hris.employees.id'), nullable=False),
        sa.Column('google_event_id', sa.String(),   nullable=True),
        sa.Column('title',           sa.String(),   nullable=False),
        sa.Column('start_datetime',  sa.DateTime(), nullable=False),
        sa.Column('end_datetime',    sa.DateTime(), nullable=False),
        sa.Column('location',        sa.String(),   nullable=True),
        sa.Column('attendees',       sa.Text(),     nullable=True),
        sa.Column('meet_link',       sa.String(),   nullable=True),
        sa.Column('html_link',       sa.String(),   nullable=True),
        sa.Column('created_at',      sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        schema='hris',
    )
    op.create_index('ix_calendar_events_employee_id', 'calendar_events', ['employee_id'], schema='hris')
    op.create_index('ix_calendar_events_start',       'calendar_events', ['start_datetime'], schema='hris')

    op.create_table(
        'calendar_event_logs',
        sa.Column('id',                sa.Integer(),  primary_key=True),
        sa.Column('employee_id',       sa.Integer(),  sa.ForeignKey('hris.employees.id'), nullable=False),
        sa.Column('calendar_event_id', sa.Integer(),  sa.ForeignKey('hris.calendar_events.id'), nullable=True),
        sa.Column('google_event_id',   sa.String(),   nullable=True),
        sa.Column('event_title',       sa.String(),   nullable=False),
        sa.Column('action',            sa.String(),   nullable=False),
        sa.Column('description',       sa.Text(),     nullable=False),
        sa.Column('created_at',        sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        schema='hris',
    )
    op.create_index('ix_calendar_event_logs_employee_id', 'calendar_event_logs', ['employee_id'], schema='hris')

    # ── 3. Crée leave_logs ────────────────────────────────
    op.create_table(
        'leave_logs',
        sa.Column('id',          sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('hris.employees.id'), nullable=False),
        sa.Column('leave_id',    sa.Integer(), sa.ForeignKey('hris.leaves.id'), nullable=True),
        sa.Column('action',      sa.String(),  nullable=False),
        sa.Column('description', sa.Text(),    nullable=False),
        sa.Column('created_at',  sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        schema='hris',
    )
    op.create_index('ix_leave_logs_employee_id', 'leave_logs', ['employee_id'], schema='hris')


def downgrade() -> None:
    op.drop_index('ix_leave_logs_employee_id',          table_name='leave_logs',          schema='hris')
    op.drop_table('leave_logs', schema='hris')
    op.drop_index('ix_calendar_event_logs_employee_id', table_name='calendar_event_logs', schema='hris')
    op.drop_table('calendar_event_logs', schema='hris')
    op.drop_index('ix_calendar_events_start',           table_name='calendar_events',     schema='hris')
    op.drop_index('ix_calendar_events_employee_id',     table_name='calendar_events',     schema='hris')
    op.drop_table('calendar_events', schema='hris')
