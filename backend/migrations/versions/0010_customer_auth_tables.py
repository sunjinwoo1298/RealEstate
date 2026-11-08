"""customer authentication and identity tables

Revision ID: 0010_customer_auth_tables
Revises: 0009_public_project_fields
Create Date: 2026-11-08 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

# revision identifiers, used by Alembic.
revision: str = '0010_customer_auth_tables'
down_revision: Union[str, None] = '0009_public_project_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

customer_account_status_enum = PGEnum(
    'PENDING_VERIFICATION', 'ACTIVE', 'SUSPENDED', 'DEACTIVATED',
    name='customer_account_status', create_type=False,
)
token_purpose_enum = PGEnum('EMAIL_VERIFICATION', 'PASSWORD_RESET', name='token_purpose', create_type=False)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE customer_account_status AS ENUM "
        "('PENDING_VERIFICATION', 'ACTIVE', 'SUSPENDED', 'DEACTIVATED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE token_purpose AS ENUM ('EMAIL_VERIFICATION', 'PASSWORD_RESET'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.create_table(
        'customer_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('normalized_email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=32), nullable=True),
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('phone_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', customer_account_status_enum, nullable=False),
        sa.Column('lead_id', sa.UUID(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('privacy_policy_accepted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('marketing_consent', sa.Boolean(), nullable=False),
        sa.Column('marketing_consent_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_customer_accounts_normalized_email', 'customer_accounts', ['normalized_email'], unique=True)
    op.create_index('ix_customer_accounts_lead_id', 'customer_accounts', ['lead_id'], unique=True)

    op.create_table(
        'customer_sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('customer_account_id', sa.UUID(), nullable=False),
        sa.Column('refresh_token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replaced_by_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['replaced_by_id'], ['customer_sessions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_account_id'], ['customer_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_customer_sessions_refresh_token_hash', 'customer_sessions', ['refresh_token_hash'], unique=True
    )
    op.create_index(
        'ix_customer_sessions_customer_account_id', 'customer_sessions', ['customer_account_id'], unique=False
    )

    op.create_table(
        'customer_verification_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('customer_account_id', sa.UUID(), nullable=False),
        sa.Column('purpose', token_purpose_enum, nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_account_id'], ['customer_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_customer_verification_tokens_token_hash', 'customer_verification_tokens', ['token_hash'], unique=True
    )
    op.create_index(
        'ix_customer_verification_tokens_customer_account_id',
        'customer_verification_tokens', ['customer_account_id'], unique=False,
    )
    op.create_index(
        'ix_customer_verification_tokens_purpose', 'customer_verification_tokens', ['purpose'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_customer_verification_tokens_purpose', table_name='customer_verification_tokens')
    op.drop_index('ix_customer_verification_tokens_customer_account_id', table_name='customer_verification_tokens')
    op.drop_index('ix_customer_verification_tokens_token_hash', table_name='customer_verification_tokens')
    op.drop_table('customer_verification_tokens')

    op.drop_index('ix_customer_sessions_customer_account_id', table_name='customer_sessions')
    op.drop_index('ix_customer_sessions_refresh_token_hash', table_name='customer_sessions')
    op.drop_table('customer_sessions')

    op.drop_index('ix_customer_accounts_lead_id', table_name='customer_accounts')
    op.drop_index('ix_customer_accounts_normalized_email', table_name='customer_accounts')
    op.drop_table('customer_accounts')

    op.execute("DROP TYPE IF EXISTS token_purpose;")
    op.execute("DROP TYPE IF EXISTS customer_account_status;")
