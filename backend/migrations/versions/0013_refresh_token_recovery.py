"""idempotent refresh-token recovery columns

Revision ID: 0013_refresh_token_recovery
Revises: 0012_customer_notifications
Create Date: 2026-11-09 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0013_refresh_token_recovery'
down_revision: Union[str, None] = '0012_customer_notifications'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ('auth_sessions', 'customer_sessions')


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column('successor_token_encrypted', sa.Text(), nullable=True))
        op.add_column(table, sa.Column('successor_recoverable_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, 'successor_recoverable_until')
        op.drop_column(table, 'successor_token_encrypted')
