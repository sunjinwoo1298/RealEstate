"""public website fields on projects (visibility, featured, public info)

Revision ID: 0009_public_project_fields
Revises: 0008_reminder_tables
Create Date: 2026-11-08 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PGEnum

# revision identifiers, used by Alembic.
revision: str = '0009_public_project_fields'
down_revision: Union[str, None] = '0008_reminder_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

project_visibility_enum = PGEnum('DRAFT', 'PUBLISHED', 'ARCHIVED', name='project_visibility', create_type=False)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE project_visibility AS ENUM ('DRAFT', 'PUBLISHED', 'ARCHIVED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.add_column(
        'projects',
        sa.Column('visibility_status', project_visibility_enum, nullable=False, server_default='DRAFT'),
    )
    op.alter_column('projects', 'visibility_status', server_default=None)
    op.create_index('ix_projects_visibility_status', 'projects', ['visibility_status'], unique=False)

    op.add_column('projects', sa.Column('is_featured', sa.Boolean(), nullable=False, server_default='false'))
    op.alter_column('projects', 'is_featured', server_default=None)

    op.add_column('projects', sa.Column('configurations', JSONB(), nullable=True))
    op.add_column('projects', sa.Column('amenities', JSONB(), nullable=True))
    op.add_column('projects', sa.Column('images', JSONB(), nullable=True))
    op.add_column('projects', sa.Column('starting_price_label', sa.String(length=120), nullable=True))
    op.add_column(
        'projects', sa.Column('price_display_approved', sa.Boolean(), nullable=False, server_default='false')
    )
    op.alter_column('projects', 'price_display_approved', server_default=None)
    op.add_column('projects', sa.Column('rera_number', sa.String(length=100), nullable=True))
    op.add_column('projects', sa.Column('floor_plan_url', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'floor_plan_url')
    op.drop_column('projects', 'rera_number')
    op.drop_column('projects', 'price_display_approved')
    op.drop_column('projects', 'starting_price_label')
    op.drop_column('projects', 'images')
    op.drop_column('projects', 'amenities')
    op.drop_column('projects', 'configurations')
    op.drop_column('projects', 'is_featured')

    op.drop_index('ix_projects_visibility_status', table_name='projects')
    op.drop_column('projects', 'visibility_status')
    op.execute("DROP TYPE IF EXISTS project_visibility;")
