"""Add event discovery fields and booking quantities.

Revision ID: 0002_discovery_quantity
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_discovery_quantity"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "category", sa.String(100), server_default="Uncategorized", nullable=False
        ),
    )
    op.add_column(
        "events",
        sa.Column("city", sa.String(120), server_default="Unknown", nullable=False),
    )
    op.create_index("ix_events_category", "events", ["category"])
    op.create_index("ix_events_city", "events", ["city"])
    op.add_column(
        "bookings",
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
    )
    op.alter_column("events", "category", server_default=None)
    op.alter_column("events", "city", server_default=None)


def downgrade() -> None:
    op.drop_column("bookings", "quantity")
    op.drop_index("ix_events_city", table_name="events")
    op.drop_index("ix_events_category", table_name="events")
    op.drop_column("events", "city")
    op.drop_column("events", "category")
