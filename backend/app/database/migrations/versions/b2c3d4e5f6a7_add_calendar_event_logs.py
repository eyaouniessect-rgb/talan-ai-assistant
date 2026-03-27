"""add calendar_event_logs table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-27

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'calendar_event_logs',
        sa.Column('id',                sa.Integer(),  primary_key=True),
        sa.Column('user_id',           sa.Integer(),  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('calendar_event_id', sa.Integer(),  sa.ForeignKey('hris.calendar_events.id'), nullable=True),
        sa.Column('google_event_id',   sa.String(),   nullable=True),
        sa.Column('event_title',       sa.String(),   nullable=False),
        sa.Column('action',            sa.String(),   nullable=False),
        sa.Column('description',       sa.Text(),     nullable=False),
        sa.Column('created_at',        sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        schema='hris',
    )
    op.create_index(
        'ix_calendar_event_logs_user_id',
        'calendar_event_logs',
        ['user_id'],
        schema='hris',
    )


def downgrade() -> None:
    op.drop_index('ix_calendar_event_logs_user_id', table_name='calendar_event_logs', schema='hris')
    op.drop_table('calendar_event_logs', schema='hris')
