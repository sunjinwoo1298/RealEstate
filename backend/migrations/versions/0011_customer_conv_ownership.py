"""customer account ownership on conversations

Revision ID: 0011_customer_conv_ownership
Revises: 0010_customer_auth_tables
Create Date: 2026-11-08 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# Kept to <=32 chars: alembic_version.version_num is varchar(32) in this
# database and a longer id fails the post-migration version-bump update
# (caught during this feature's implementation).
revision: str = '0011_customer_conv_ownership'
down_revision: Union[str, None] = '0010_customer_auth_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable so every existing (and future anonymous-buyer) conversation
    # remains valid with customer_account_id = NULL, per spec section 2/12.
    op.add_column('conversations', sa.Column('customer_account_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_conversations_customer_account_id',
        'conversations', 'customer_accounts',
        ['customer_account_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_conversations_customer_account_id', 'conversations', ['customer_account_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_conversations_customer_account_id', table_name='conversations')
    op.drop_constraint('fk_conversations_customer_account_id', 'conversations', type_='foreignkey')
    op.drop_column('conversations', 'customer_account_id')
