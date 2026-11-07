"""knowledge management (pgvector RAG) and lead qualification tables

Revision ID: 0005_knowledge_qual_tables
Revises: 0004_conversation_chat_tables
Create Date: 2026-11-07 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB

from backend.core.config import settings

# revision identifiers, used by Alembic.
revision: str = '0005_knowledge_qual_tables'
down_revision: Union[str, None] = '0004_conversation_chat_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

approval_status_enum = PGEnum('DRAFT', 'APPROVED', 'ARCHIVED', name='approval_status', create_type=False)
qualification_configuration_enum = PGEnum('BHK_2', 'BHK_3', name='qualification_configuration', create_type=False)
purchase_purpose_enum = PGEnum('SELF_USE', 'INVESTMENT', name='purchase_purpose', create_type=False)
conversation_language_enum = PGEnum('EN', 'HI', 'GU', name='conversation_language', create_type=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE approval_status AS ENUM ('DRAFT', 'APPROVED', 'ARCHIVED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE qualification_configuration AS ENUM ('BHK_2', 'BHK_3'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE purchase_purpose AS ENUM ('SELF_USE', 'INVESTMENT'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.create_table(
        'projects',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index('ix_projects_name', 'projects', ['name'], unique=True)

    op.create_table(
        'knowledge_documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('approval_status', approval_status_enum, nullable=False),
        sa.Column('source_filename', sa.String(length=255), nullable=True),
        sa.Column('uploaded_by', sa.UUID(), nullable=True),
        sa.Column('approved_by', sa.UUID(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_knowledge_documents_project_id', 'knowledge_documents', ['project_id'], unique=False)

    op.create_table(
        'knowledge_chunks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(settings.EMBEDDING_DIMENSION), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('extra_metadata', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_knowledge_chunks_document_id', 'knowledge_chunks', ['document_id'], unique=False)
    op.create_index('ix_knowledge_chunks_project_id', 'knowledge_chunks', ['project_id'], unique=False)

    op.create_table(
        'lead_qualifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('lead_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('configuration', qualification_configuration_enum, nullable=True),
        sa.Column('budget_min', sa.Numeric(14, 2), nullable=True),
        sa.Column('budget_max', sa.Numeric(14, 2), nullable=True),
        sa.Column('purchase_purpose', purchase_purpose_enum, nullable=True),
        sa.Column('preferred_language', conversation_language_enum, nullable=True),
        sa.Column('preferred_visit_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lead_id'),
    )
    op.create_index('ix_lead_qualifications_lead_id', 'lead_qualifications', ['lead_id'], unique=True)
    op.create_index('ix_lead_qualifications_project_id', 'lead_qualifications', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_lead_qualifications_project_id', table_name='lead_qualifications')
    op.drop_index('ix_lead_qualifications_lead_id', table_name='lead_qualifications')
    op.drop_table('lead_qualifications')

    op.drop_index('ix_knowledge_chunks_project_id', table_name='knowledge_chunks')
    op.drop_index('ix_knowledge_chunks_document_id', table_name='knowledge_chunks')
    op.drop_table('knowledge_chunks')

    op.drop_index('ix_knowledge_documents_project_id', table_name='knowledge_documents')
    op.drop_table('knowledge_documents')

    op.drop_index('ix_projects_name', table_name='projects')
    op.drop_table('projects')

    op.execute("DROP TYPE IF EXISTS purchase_purpose;")
    op.execute("DROP TYPE IF EXISTS qualification_configuration;")
    op.execute("DROP TYPE IF EXISTS approval_status;")
