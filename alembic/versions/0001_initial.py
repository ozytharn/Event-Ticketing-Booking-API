"""Create users, events, and bookings.

Revision ID: 0001_initial
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(9), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organizer_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("venue", sa.String(250), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("booked_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.CheckConstraint("capacity > 0", name="ck_events_capacity_positive"),
        sa.CheckConstraint(
            "booked_count >= 0 AND booked_count <= capacity", name="ck_events_seat_count"
        ),
        sa.CheckConstraint("price >= 0", name="ck_events_price_nonnegative"),
    )
    op.create_index("ix_events_organizer_id", "events", ["organizer_id"])
    op.create_index("ix_events_title", "events", ["title"])
    op.create_index("ix_events_starts_at", "events", ["starts_at"])
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "attendee_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("amount_paid", sa.Numeric(10, 2), nullable=False),
        sa.Column("refund_status", sa.String(12), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_id", "attendee_id", name="uq_booking_event_attendee"),
    )
    op.create_index("ix_bookings_event_id", "bookings", ["event_id"])
    op.create_index("ix_bookings_attendee_id", "bookings", ["attendee_id"])


def downgrade() -> None:
    op.drop_index("ix_bookings_attendee_id", table_name="bookings")
    op.drop_index("ix_bookings_event_id", table_name="bookings")
    op.drop_table("bookings")
    op.drop_index("ix_events_starts_at", table_name="events")
    op.drop_index("ix_events_title", table_name="events")
    op.drop_index("ix_events_organizer_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
