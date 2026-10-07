"""Support user account lifecycle and booking updates.

Revision ID: 0003_user_booking_update
Revises: 0002_discovery_quantity
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_user_booking_update"
down_revision: str | None = "0002_discovery_quantity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False)
    )
    op.add_column(
        "bookings",
        sa.Column(
            "unit_price",
            sa.Numeric(10, 2),
            server_default="0.00",
            nullable=False,
        ),
    )
    op.execute("UPDATE bookings SET unit_price = amount_paid / quantity")
    op.create_check_constraint(
        "ck_bookings_quantity_positive", "bookings", "quantity > 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_bookings_quantity_positive", "bookings", type_="check")
    op.drop_column("bookings", "unit_price")
    op.drop_column("users", "is_active")
