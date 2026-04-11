"""Ajout de project_management.project_documents

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-04-10

Changements :
  - project_management.project_documents :
      stockage des CDC uploadés par les PMs.
      file_hash (SHA-256) pour déduplication.
      Référencé par le pipeline via document_id dans l'état du graph.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'h2i3j4k5l6m7'
down_revision: Union[str, None] = 'g1h2i3j4k5l6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table(
        'project_documents',
        sa.Column('id',          sa.Integer(),    primary_key=True),
        sa.Column('project_id',  sa.Integer(),    sa.ForeignKey('crm.projects.id'),    nullable=False),
        sa.Column('file_name',   sa.String(),     nullable=False),
        sa.Column('file_path',   sa.String(),     nullable=False),
        sa.Column('file_hash',   sa.String(64),   nullable=False),   # SHA-256 hex
        sa.Column('file_size',   sa.BigInteger(), nullable=False),
        sa.Column('mime_type',   sa.String(),     nullable=True),
        sa.Column('uploaded_by', sa.Integer(),    sa.ForeignKey('hris.employees.id'), nullable=True),
        sa.Column('created_at',  sa.DateTime(),   server_default=sa.text('now()'), nullable=False),
        schema='project_management',
    )

    op.create_index(
        'ix_project_documents_project_id',
        'project_documents', ['project_id'],
        schema='project_management',
    )

    # Index sur file_hash pour la détection rapide de doublons
    op.create_index(
        'ix_project_documents_file_hash',
        'project_documents', ['file_hash'],
        schema='project_management',
    )


def downgrade() -> None:
    op.drop_index('ix_project_documents_file_hash',   table_name='project_documents', schema='project_management')
    op.drop_index('ix_project_documents_project_id',  table_name='project_documents', schema='project_management')
    op.drop_table('project_documents', schema='project_management')
