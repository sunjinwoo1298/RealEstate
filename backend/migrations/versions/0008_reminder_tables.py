"""visit reminders table and site_visits.booking_version

Revision ID: 0008_reminder_tables
Revises: 0007_handoff_tables
Create Date: 2026-11-07 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

# revision identifiers, used by Alembic.
revision: str = '0008_reminder_tables'
down_revision: Union[str, None] = '0007_handoff_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

reminder_type_enum = PGEnum('24H', '2H', name='reminder_type', create_type=False)
reminder_status_enum = PGEnum(
    'SCHEDULED', 'PROCESSING', 'SENT', 'SIMULATED', 'FAILED', 'CANCELLED', 'SKIPPED',
    name='reminder_status', create_type=False,
)


def upgrade() -> None:
    op.add_column(
        'site_visits', sa.Column('booking_version', sa.Integer(), nullable=False, server_default='1')
    )
    op.alter_column('site_visits', 'booking_version', server_default=None)

    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE reminder_type AS ENUM ('24H', '2H'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE reminder_status AS ENUM "
        "('SCHEDULED', 'PROCESSING', 'SENT', 'SIMULATED', 'FAILED', 'CANCELLED', 'SKIPPED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.create_table(
        'visit_reminders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('site_visit_id', sa.UUID(), nullable=False),
        sa.Column('reminder_type', reminder_type_enum, nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', reminder_status_enum, nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('booking_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['site_visit_id'], ['site_visits.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'site_visit_id', 'reminder_type', 'booking_version', name='uq_visit_reminders_booking_version'
        ),
    )
    op.create_index('ix_visit_reminders_site_visit_id', 'visit_reminders', ['site_visit_id'], unique=False)
    op.create_index('ix_visit_reminders_scheduled_at', 'visit_reminders', ['scheduled_at'], unique=False)
    op.create_index('ix_visit_reminders_status', 'visit_reminders', ['status'], unique=False)
    # Composite index matching the worker's due-reminder claim query (status + scheduled_at).
    op.create_index(
        'ix_visit_reminders_status_scheduled_at', 'visit_reminders', ['status', 'scheduled_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_visit_reminders_status_scheduled_at', table_name='visit_reminders')
    op.drop_index('ix_visit_reminders_status', table_name='visit_reminders')
    op.drop_index('ix_visit_reminders_scheduled_at', table_name='visit_reminders')
    op.drop_index('ix_visit_reminders_site_visit_id', table_name='visit_reminders')
    op.drop_table('visit_reminders')

    op.execute("DROP TYPE IF EXISTS reminder_status;")
    op.execute("DROP TYPE IF EXISTS reminder_type;")

    op.drop_column('site_visits', 'booking_version')
