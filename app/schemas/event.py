from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.event import EventStatus


class EventFields(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=120)
    venue: str = Field(min_length=1, max_length=250)
    starts_at: datetime
    ends_at: datetime
    capacity: int = Field(gt=0)
    price: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    status: EventStatus = EventStatus.PUBLISHED

    @model_validator(mode="after")
    def validate_event_times(self) -> "EventFields":
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be earlier than ends_at")
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("event datetimes must include a timezone")
        if self.starts_at.astimezone(UTC) <= datetime.now(UTC):
            raise ValueError("starts_at must be in the future")
        return self


class EventCreate(EventFields):
    pass


class EventUpdate(EventFields):
    @model_validator(mode="after")
    def cannot_cancel_via_update(self) -> "EventUpdate":
        if self.status == EventStatus.CANCELLED:
            raise ValueError("cancel events with DELETE /api/v1/events/{event_id}")
        return self


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organizer_id: int
    title: str
    description: str
    category: str
    city: str
    venue: str
    starts_at: datetime
    ends_at: datetime
    capacity: int
    booked_count: int
    price: Decimal
    currency: str
    status: EventStatus
    available_seats: int

    @classmethod
    def from_event(cls, event: object) -> "EventRead":
        return cls.model_validate(
            {
                **{
                    key: getattr(event, key) for key in cls.model_fields if key != "available_seats"
                },
                "available_seats": event.capacity - event.booked_count,
            }
        )
