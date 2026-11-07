"""handoffs, conversation assignments and notifications

Revision ID: 0007_handoff_tables
Revises: 0006_availability_booking_tables
Create Date: 2026-11-07 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB

# revision identifiers, used by Alembic.
revision: str = '0007_handoff_tables'
down_revision: Union[str, None] = '0006_availability_booking_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

handoff_status_enum = PGEnum(
    'PENDING', 'ASSIGNED', 'ACCEPTED', 'RESOLVED', 'CANCELLED', name='handoff_status', create_type=False
)
handoff_reason_enum = PGEnum(
    'BUYER_REQUEST', 'UNSUPPORTED_QUERY', 'LOW_CONFIDENCE', 'COMPLAINT', 'OTHER', name='handoff_reason', create_type=False
)
assignment_status_enum = PGEnum(
    'ASSIGNED', 'ACCEPTED', 'REJECTED', 'ENDED', name='assignment_status', create_type=False
)
notification_type_enum = PGEnum('HANDOFF_ASSIGNED', name='notification_type', create_type=False)
notification_status_enum = PGEnum('PENDING', 'SENT', 'FAILED', name='notification_status', create_type=False)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE handoff_status AS ENUM ('PENDING', 'ASSIGNED', 'ACCEPTED', 'RESOLVED', 'CANCELLED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE handoff_reason AS ENUM ('BUYER_REQUEST', 'UNSUPPORTED_QUERY', 'LOW_CONFIDENCE', 'COMPLAINT', 'OTHER'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE assignment_status AS ENUM ('ASSIGNED', 'ACCEPTED', 'REJECTED', 'ENDED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE notification_type AS ENUM ('HANDOFF_ASSIGNED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE notification_status AS ENUM ('PENDING', 'SENT', 'FAILED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.create_table(
        'handoffs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('lead_id', sa.UUID(), nullable=False),
        sa.Column('assigned_executive_id', sa.UUID(), nullable=True),
        sa.Column('status', handoff_status_enum, nullable=False),
        sa.Column('reason', handoff_reason_enum, nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_executive_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_handoffs_conversation_id', 'handoffs', ['conversation_id'], unique=False)
    op.create_index('ix_handoffs_lead_id', 'handoffs', ['lead_id'], unique=False)
    op.create_index('ix_handoffs_assigned_executive_id', 'handoffs', ['assigned_executive_id'], unique=False)
    # At most one non-terminal handoff per conversation at a time.
    op.execute(
        "CREATE UNIQUE INDEX uq_handoffs_active_per_conversation ON handoffs (conversation_id) "
        "WHERE status IN ('PENDING', 'ASSIGNED', 'ACCEPTED');"
    )

    op.create_table(
        'conversation_assignments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('handoff_id', sa.UUID(), nullable=False),
        sa.Column('executive_id', sa.UUID(), nullable=True),
        sa.Column('assigned_by', sa.UUID(), nullable=True),
        sa.Column('status', assignment_status_enum, nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['handoff_id'], ['handoffs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['executive_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_conversation_assignments_conversation_id', 'conversation_assignments', ['conversation_id'], unique=False)
    op.create_index('ix_conversation_assignments_handoff_id', 'conversation_assignments', ['handoff_id'], unique=False)
    op.create_index('ix_conversation_assignments_executive_id', 'conversation_assignments', ['executive_id'], unique=False)
    # At most one active (ASSIGNED/ACCEPTED) assignment per conversation at a time.
    op.execute(
        "CREATE UNIQUE INDEX uq_conversation_assignments_active_per_conversation ON conversation_assignments (conversation_id) "
        "WHERE status IN ('ASSIGNED', 'ACCEPTED');"
    )

    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('recipient_id', sa.UUID(), nullable=False),
        sa.Column('notification_type', notification_type_enum, nullable=False),
        sa.Column('reference_id', sa.UUID(), nullable=False),
        sa.Column('status', notification_status_enum, nullable=False),
        sa.Column('payload', JSONB, nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recipient_id', 'reference_id', 'notification_type', name='uq_notifications_dedupe'),
    )
    op.create_index('ix_notifications_recipient_id', 'notifications', ['recipient_id'], unique=False)
    op.create_index('ix_notifications_reference_id', 'notifications', ['reference_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notifications_reference_id', table_name='notifications')
    op.drop_index('ix_notifications_recipient_id', table_name='notifications')
    op.drop_table('notifications')

    op.execute('DROP INDEX IF EXISTS uq_conversation_assignments_active_per_conversation;')
    op.drop_index('ix_conversation_assignments_executive_id', table_name='conversation_assignments')
    op.drop_index('ix_conversation_assignments_handoff_id', table_name='conversation_assignments')
    op.drop_index('ix_conversation_assignments_conversation_id', table_name='conversation_assignments')
    op.drop_table('conversation_assignments')

    op.execute('DROP INDEX IF EXISTS uq_handoffs_active_per_conversation;')
    op.drop_index('ix_handoffs_assigned_executive_id', table_name='handoffs')
    op.drop_index('ix_handoffs_lead_id', table_name='handoffs')
    op.drop_index('ix_handoffs_conversation_id', table_name='handoffs')
    op.drop_table('handoffs')

    op.execute("DROP TYPE IF EXISTS notification_status;")
    op.execute("DROP TYPE IF EXISTS notification_type;")
    op.execute("DROP TYPE IF EXISTS assignment_status;")
    op.execute("DROP TYPE IF EXISTS handoff_reason;")
    op.execute("DROP TYPE IF EXISTS handoff_status;")
