from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.event import Event


class UserRole(StrEnum):
    ATTENDEE = "attendee"
    ORGANIZER = "organizer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=UserRole.ATTENDEE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)

    events: Mapped[list["Event"]] = relationship(back_populates="organizer")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="attendee")
