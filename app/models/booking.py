from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class BookingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class RefundStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    REFUNDED = "refunded"


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("event_id", "attendee_id", name="uq_booking_event_attendee"),
        CheckConstraint("quantity > 0", name="ck_bookings_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"), index=True)
    attendee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[int] = mapped_column(default=1, server_default="1")
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), server_default="0.00"
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            native_enum=False,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=BookingStatus.CONFIRMED,
    )
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    refund_status: Mapped[RefundStatus] = mapped_column(
        Enum(
            RefundStatus,
            name="refund_status",
            native_enum=False,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=RefundStatus.NOT_REQUIRED,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped["Event"] = relationship(back_populates="bookings")
    attendee: Mapped["User"] = relationship(back_populates="bookings")
