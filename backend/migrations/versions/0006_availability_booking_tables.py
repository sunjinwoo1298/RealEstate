"""availability rules, blocked periods, project visit capacity, site visits and visit events

Revision ID: 0006_availability_booking_tables
Revises: 0005_knowledge_qual_tables
Create Date: 2026-11-07 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB

# revision identifiers, used by Alembic.
revision: str = '0006_availability_booking_tables'
down_revision: Union[str, None] = '0005_knowledge_qual_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

site_visit_status_enum = PGEnum('CONFIRMED', 'CANCELLED', 'COMPLETED', 'NO_SHOW', name='site_visit_status', create_type=False)
visit_event_type_enum = PGEnum('BOOKED', 'CANCELLED', 'RESCHEDULED', 'ATTENDANCE_MARKED', name='visit_event_type', create_type=False)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE site_visit_status AS ENUM ('CONFIRMED', 'CANCELLED', 'COMPLETED', 'NO_SHOW'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE visit_event_type AS ENUM ('BOOKED', 'CANCELLED', 'RESCHEDULED', 'ATTENDANCE_MARKED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.create_table(
        'availability_rules',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('executive_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('day_of_week', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('day_of_week >= 0 AND day_of_week <= 6', name='ck_availability_rules_day_of_week'),
        sa.CheckConstraint('end_time > start_time', name='ck_availability_rules_end_after_start'),
        sa.ForeignKeyConstraint(['executive_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_availability_rules_executive_id', 'availability_rules', ['executive_id'], unique=False)
    op.create_index('ix_availability_rules_project_id', 'availability_rules', ['project_id'], unique=False)

    op.create_table(
        'blocked_periods',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('executive_id', sa.UUID(), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('end_time > start_time', name='ck_blocked_periods_end_after_start'),
        sa.ForeignKeyConstraint(['executive_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_blocked_periods_executive_id', 'blocked_periods', ['executive_id'], unique=False)

    op.create_table(
        'project_visit_capacities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('capacity', sa.Integer(), nullable=False),
        sa.Column('visit_duration_minutes', sa.Integer(), nullable=False),
        sa.Column('buffer_minutes', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('capacity > 0', name='ck_project_visit_capacities_capacity_positive'),
        sa.CheckConstraint('visit_duration_minutes > 0', name='ck_project_visit_capacities_duration_positive'),
        sa.CheckConstraint('buffer_minutes >= 0', name='ck_project_visit_capacities_buffer_non_negative'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id'),
    )

    op.create_table(
        'site_visits',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('lead_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('executive_id', sa.UUID(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', site_visit_status_enum, nullable=False),
        sa.Column('booking_reference', sa.String(length=32), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('end_time > start_time', name='ck_site_visits_end_after_start'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['executive_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('booking_reference'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index('ix_site_visits_lead_id', 'site_visits', ['lead_id'], unique=False)
    op.create_index('ix_site_visits_project_id', 'site_visits', ['project_id'], unique=False)
    op.create_index('ix_site_visits_executive_id', 'site_visits', ['executive_id'], unique=False)
    op.create_index('ix_site_visits_start_time', 'site_visits', ['start_time'], unique=False)

    op.create_table(
        'visit_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('site_visit_id', sa.UUID(), nullable=False),
        sa.Column('event_type', visit_event_type_enum, nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('extra_metadata', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['site_visit_id'], ['site_visits.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_visit_events_site_visit_id', 'visit_events', ['site_visit_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_visit_events_site_visit_id', table_name='visit_events')
    op.drop_table('visit_events')

    op.drop_index('ix_site_visits_start_time', table_name='site_visits')
    op.drop_index('ix_site_visits_executive_id', table_name='site_visits')
    op.drop_index('ix_site_visits_project_id', table_name='site_visits')
    op.drop_index('ix_site_visits_lead_id', table_name='site_visits')
    op.drop_table('site_visits')

    op.drop_table('project_visit_capacities')

    op.drop_index('ix_blocked_periods_executive_id', table_name='blocked_periods')
    op.drop_table('blocked_periods')

    op.drop_index('ix_availability_rules_project_id', table_name='availability_rules')
    op.drop_index('ix_availability_rules_executive_id', table_name='availability_rules')
    op.drop_table('availability_rules')

    op.execute("DROP TYPE IF EXISTS visit_event_type;")
    op.execute("DROP TYPE IF EXISTS site_visit_status;")
