"""conversation persistence and buyer chat tables

Revision ID: 0004_conversation_chat_tables
Revises: 0003_lead_management_tables
Create Date: 2026-11-07 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB


# revision identifiers, used by Alembic.
revision: str = '0004_conversation_chat_tables'
down_revision: Union[str, None] = '0003_lead_management_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

channel_type_enum = PGEnum('WEB_CHAT', name='channel_type', create_type=False)
conversation_status_enum = PGEnum('ACTIVE', 'CLOSED', name='conversation_status', create_type=False)
ownership_status_enum = PGEnum(
    'AI_ACTIVE', 'PENDING_ASSIGNMENT', 'HUMAN_ACTIVE', 'RESOLVED', name='ownership_status', create_type=False
)
conversation_language_enum = PGEnum('EN', 'HI', 'GU', name='conversation_language', create_type=False)
conversation_state_enum = PGEnum(
    'DISCOVERY', 'QUALIFIED', 'VISIT_REQUESTED', 'VISIT_BOOKED', name='conversation_state', create_type=False
)
sender_type_enum = PGEnum('BUYER', 'AI', 'STAFF', 'SYSTEM', name='sender_type', create_type=False)
message_type_enum = PGEnum('TEXT', 'SYSTEM_EVENT', name='message_type', create_type=False)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE channel_type AS ENUM ('WEB_CHAT'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE conversation_status AS ENUM ('ACTIVE', 'CLOSED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE ownership_status AS ENUM ('AI_ACTIVE', 'PENDING_ASSIGNMENT', 'HUMAN_ACTIVE', 'RESOLVED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE conversation_language AS ENUM ('EN', 'HI', 'GU'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE conversation_state AS ENUM ('DISCOVERY', 'QUALIFIED', 'VISIT_REQUESTED', 'VISIT_BOOKED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE sender_type AS ENUM ('BUYER', 'AI', 'STAFF', 'SYSTEM'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE message_type AS ENUM ('TEXT', 'SYSTEM_EVENT'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.create_table(
        'conversations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('lead_id', sa.UUID(), nullable=False),
        sa.Column('channel', channel_type_enum, nullable=False),
        sa.Column('status', conversation_status_enum, nullable=False),
        sa.Column('ownership_status', ownership_status_enum, nullable=False),
        sa.Column('language', conversation_language_enum, nullable=False),
        sa.Column('conversation_state', conversation_state_enum, nullable=False),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_conversations_lead_id', 'conversations', ['lead_id'], unique=False)

    op.create_table(
        'messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('sender_type', sender_type_enum, nullable=False),
        sa.Column('sender_id', sa.UUID(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('message_type', message_type_enum, nullable=False),
        sa.Column('extra_metadata', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'], unique=False)
    op.create_index('ix_messages_created_at', 'messages', ['created_at'], unique=False)
    op.create_index(
        'ix_messages_conversation_id_created_at', 'messages', ['conversation_id', 'created_at'], unique=False
    )

    op.create_table(
        'buyer_sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_buyer_sessions_conversation_id', 'buyer_sessions', ['conversation_id'], unique=False)
    op.create_index('ix_buyer_sessions_token_hash', 'buyer_sessions', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_buyer_sessions_token_hash', table_name='buyer_sessions')
    op.drop_index('ix_buyer_sessions_conversation_id', table_name='buyer_sessions')
    op.drop_table('buyer_sessions')

    op.drop_index('ix_messages_conversation_id_created_at', table_name='messages')
    op.drop_index('ix_messages_created_at', table_name='messages')
    op.drop_index('ix_messages_conversation_id', table_name='messages')
    op.drop_table('messages')

    op.drop_index('ix_conversations_lead_id', table_name='conversations')
    op.drop_table('conversations')

    op.execute("DROP TYPE IF EXISTS message_type;")
    op.execute("DROP TYPE IF EXISTS sender_type;")
    op.execute("DROP TYPE IF EXISTS conversation_state;")
    op.execute("DROP TYPE IF EXISTS conversation_language;")
    op.execute("DROP TYPE IF EXISTS ownership_status;")
    op.execute("DROP TYPE IF EXISTS conversation_status;")
    op.execute("DROP TYPE IF EXISTS channel_type;")
