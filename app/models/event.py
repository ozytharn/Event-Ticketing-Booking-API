from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.user import User


class EventStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_events_capacity_positive"),
        CheckConstraint(
            "booked_count >= 0 AND booked_count <= capacity", name="ck_events_seat_count"
        ),
        CheckConstraint("price >= 0", name="ck_events_price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organizer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100), index=True)
    city: Mapped[str] = mapped_column(String(120), index=True)
    venue: Mapped[str] = mapped_column(String(250))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int] = mapped_column(Integer)
    booked_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    status: Mapped[EventStatus] = mapped_column(
        Enum(
            EventStatus,
            name="event_status",
            native_enum=False,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=EventStatus.PUBLISHED,
    )

    organizer: Mapped["User"] = relationship(back_populates="events")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="event")
