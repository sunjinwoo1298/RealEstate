"""customer notification deliveries (outbox) and email preferences

Revision ID: 0012_customer_notifications
Revises: 0011_customer_conv_ownership
Create Date: 2026-11-09 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB

# revision identifiers, used by Alembic. (<=32 chars: alembic_version is varchar(32))
revision: str = '0012_customer_notifications'
down_revision: Union[str, None] = '0011_customer_conv_ownership'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

event_enum = PGEnum(
    'SITE_VISIT_BOOKED', 'SITE_VISIT_RESCHEDULED', 'SITE_VISIT_CANCELLED',
    'SITE_VISIT_REMINDER_24H', 'SITE_VISIT_REMINDER_2H',
    name='customer_notification_event', create_type=False,
)
channel_enum = PGEnum('EMAIL', name='customer_notification_channel', create_type=False)
status_enum = PGEnum(
    'PENDING', 'PROCESSING', 'SENT', 'SIMULATED', 'FAILED', 'CANCELLED', 'SKIPPED',
    name='customer_delivery_status', create_type=False,
)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE customer_notification_event AS ENUM "
        "('SITE_VISIT_BOOKED', 'SITE_VISIT_RESCHEDULED', 'SITE_VISIT_CANCELLED', "
        "'SITE_VISIT_REMINDER_24H', 'SITE_VISIT_REMINDER_2H'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE customer_notification_channel AS ENUM ('EMAIL'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE customer_delivery_status AS ENUM "
        "('PENDING', 'PROCESSING', 'SENT', 'SIMULATED', 'FAILED', 'CANCELLED', 'SKIPPED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )

    op.add_column(
        'customer_accounts',
        sa.Column('transactional_email_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )
    op.add_column(
        'customer_accounts',
        sa.Column('notification_preferences_updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'customer_notification_deliveries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('customer_account_id', sa.UUID(), nullable=False),
        sa.Column('lead_id', sa.UUID(), nullable=True),
        sa.Column('site_visit_id', sa.UUID(), nullable=True),
        sa.Column('visit_reminder_id', sa.UUID(), nullable=True),
        sa.Column('booking_version', sa.Integer(), nullable=True),
        sa.Column('event_type', event_enum, nullable=False),
        sa.Column('channel', channel_enum, nullable=False),
        sa.Column('recipient', sa.String(length=255), nullable=False),
        sa.Column('template_key', sa.String(length=64), nullable=False),
        sa.Column('payload', JSONB(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=160), nullable=False),
        sa.Column('status', status_enum, nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_account_id'], ['customer_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['site_visit_id'], ['site_visits.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['visit_reminder_id'], ['visit_reminders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_cnd_idempotency_key'),
        sa.UniqueConstraint('visit_reminder_id', name='uq_cnd_visit_reminder_id'),
    )
    op.create_index('ix_cnd_claim', 'customer_notification_deliveries', ['status', 'next_attempt_at'])
    op.create_index(
        'ix_cnd_customer_history', 'customer_notification_deliveries', ['customer_account_id', 'created_at']
    )
    op.create_index('ix_cnd_lead_id', 'customer_notification_deliveries', ['lead_id'])
    op.create_index('ix_cnd_site_visit_id', 'customer_notification_deliveries', ['site_visit_id'])


def downgrade() -> None:
    op.drop_index('ix_cnd_site_visit_id', table_name='customer_notification_deliveries')
    op.drop_index('ix_cnd_lead_id', table_name='customer_notification_deliveries')
    op.drop_index('ix_cnd_customer_history', table_name='customer_notification_deliveries')
    op.drop_index('ix_cnd_claim', table_name='customer_notification_deliveries')
    op.drop_table('customer_notification_deliveries')
    op.drop_column('customer_accounts', 'notification_preferences_updated_at')
    op.drop_column('customer_accounts', 'transactional_email_enabled')
    op.execute("DROP TYPE IF EXISTS customer_delivery_status")
    op.execute("DROP TYPE IF EXISTS customer_notification_channel")
    op.execute("DROP TYPE IF EXISTS customer_notification_event")
