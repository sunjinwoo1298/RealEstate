"""initial baseline

Revision ID: 0001_initial_baseline
Revises: 
Create Date: 2026-11-06 18:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_initial_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline foundation migration - no business-domain tables created yet per Feature 00 specification
    pass


def downgrade() -> None:
    pass

