"""lead ingestion and deduplication tables

Revision ID: 0003_lead_management_tables
Revises: 0002_auth_rbac_tables
Create Date: 2026-11-07 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB


# revision identifiers, used by Alembic.
revision: str = '0003_lead_management_tables'
down_revision: Union[str, None] = '0002_auth_rbac_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

lead_status_enum = PGEnum(
    'NEW', 'AI_CONTACTED', 'QUALIFIED', 'VISIT_REQUESTED', 'VISIT_BOOKED',
    'VISIT_COMPLETED', 'CONVERTED', 'LOST', 'OPTED_OUT',
    name='lead_status', create_type=False,
)
consent_status_enum = PGEnum('GRANTED', 'DECLINED', 'NOT_RECORDED', name='consent_status', create_type=False)
source_type_enum = PGEnum(
    'WEBSITE', 'PROPERTY_PORTAL', 'SOCIAL_AD', 'HOARDING', 'MANUAL', 'CSV_IMPORT',
    name='source_type', create_type=False,
)
duplicate_review_status_enum = PGEnum(
    'PENDING_REVIEW', 'CONFIRMED_DUPLICATE', 'REJECTED', name='duplicate_review_status', create_type=False
)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE lead_status AS ENUM ('NEW', 'AI_CONTACTED', 'QUALIFIED', 'VISIT_REQUESTED', "
        "'VISIT_BOOKED', 'VISIT_COMPLETED', 'CONVERTED', 'LOST', 'OPTED_OUT'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE consent_status AS ENUM ('GRANTED', 'DECLINED', 'NOT_RECORDED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE source_type AS ENUM ('WEBSITE', 'PROPERTY_PORTAL', 'SOCIAL_AD', 'HOARDING', 'MANUAL', 'CSV_IMPORT'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE duplicate_review_status AS ENUM ('PENDING_REVIEW', 'CONFIRMED_DUPLICATE', 'REJECTED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.create_table(
        'leads',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('normalized_phone', sa.String(length=20), nullable=True),
        sa.Column('normalized_email', sa.String(length=255), nullable=True),
        sa.Column('preferred_language', sa.String(length=10), nullable=True),
        sa.Column('lead_status', lead_status_enum, nullable=False),
        sa.Column('assigned_executive_id', sa.UUID(), nullable=True),
        sa.Column('consent_status', consent_status_enum, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['assigned_executive_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_leads_normalized_phone', 'leads', ['normalized_phone'], unique=False)
    op.create_index('ix_leads_normalized_email', 'leads', ['normalized_email'], unique=False)
    op.create_index('ix_leads_assigned_executive_id', 'leads', ['assigned_executive_id'], unique=False)
    # Partial unique indexes: dedup identity constraints, NULLs excluded so
    # multiple leads may legitimately have no phone/email on file.
    op.execute(
        "CREATE UNIQUE INDEX uq_leads_normalized_phone ON leads (normalized_phone) "
        "WHERE normalized_phone IS NOT NULL;"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_leads_normalized_email ON leads (normalized_email) "
        "WHERE normalized_email IS NOT NULL;"
    )

    op.create_table(
        'lead_sources',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('lead_id', sa.UUID(), nullable=False),
        sa.Column('source_type', source_type_enum, nullable=False),
        sa.Column('external_lead_id', sa.String(length=255), nullable=True),
        sa.Column('campaign_name', sa.String(length=255), nullable=True),
        sa.Column('raw_payload', JSONB, nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lead_sources_lead_id', 'lead_sources', ['lead_id'], unique=False)
    op.create_index('ix_lead_sources_source_type', 'lead_sources', ['source_type'], unique=False)
    op.execute(
        "CREATE UNIQUE INDEX uq_lead_sources_source_external_id ON lead_sources (source_type, external_lead_id) "
        "WHERE external_lead_id IS NOT NULL;"
    )

    op.create_table(
        'webhook_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('source_type', source_type_enum, nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('lead_source_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['lead_source_id'], ['lead_sources.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_webhook_events_source_type', 'webhook_events', ['source_type'], unique=False)
    op.create_unique_constraint(
        'uq_webhook_events_source_idempotency_key', 'webhook_events', ['source_type', 'idempotency_key']
    )

    op.create_table(
        'potential_duplicate_matches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('new_lead_id', sa.UUID(), nullable=False),
        sa.Column('existing_lead_id', sa.UUID(), nullable=False),
        sa.Column('match_reason', sa.String(length=100), nullable=False),
        sa.Column('similarity_score', sa.Float(), nullable=True),
        sa.Column('status', duplicate_review_status_enum, nullable=False),
        sa.Column('reviewed_by_id', sa.UUID(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['new_lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['existing_lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_potential_duplicate_matches_new_lead_id', 'potential_duplicate_matches', ['new_lead_id'], unique=False)
    op.create_index('ix_potential_duplicate_matches_existing_lead_id', 'potential_duplicate_matches', ['existing_lead_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_potential_duplicate_matches_existing_lead_id', table_name='potential_duplicate_matches')
    op.drop_index('ix_potential_duplicate_matches_new_lead_id', table_name='potential_duplicate_matches')
    op.drop_table('potential_duplicate_matches')

    op.drop_constraint('uq_webhook_events_source_idempotency_key', 'webhook_events', type_='unique')
    op.drop_index('ix_webhook_events_source_type', table_name='webhook_events')
    op.drop_table('webhook_events')

    op.execute('DROP INDEX IF EXISTS uq_lead_sources_source_external_id;')
    op.drop_index('ix_lead_sources_source_type', table_name='lead_sources')
    op.drop_index('ix_lead_sources_lead_id', table_name='lead_sources')
    op.drop_table('lead_sources')

    op.execute('DROP INDEX IF EXISTS uq_leads_normalized_email;')
    op.execute('DROP INDEX IF EXISTS uq_leads_normalized_phone;')
    op.drop_index('ix_leads_assigned_executive_id', table_name='leads')
    op.drop_index('ix_leads_normalized_email', table_name='leads')
    op.drop_index('ix_leads_normalized_phone', table_name='leads')
    op.drop_table('leads')

    op.execute("DROP TYPE IF EXISTS duplicate_review_status;")
    op.execute("DROP TYPE IF EXISTS source_type;")
    op.execute("DROP TYPE IF EXISTS consent_status;")
    op.execute("DROP TYPE IF EXISTS lead_status;")
