from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.booking import BookingStatus, RefundStatus


class BookingCreate(BaseModel):
    quantity: int = Field(default=1, ge=1)


class BookingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=1)


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    attendee_id: int
    quantity: int
    unit_price: Decimal
    status: BookingStatus
    amount_paid: Decimal
    refund_status: RefundStatus
    created_at: datetime
    cancelled_at: datetime | None
    refunded_at: datetime | None


class EventSalesSummary(BaseModel):
    event_id: int
    tickets_sold: int
    revenue: Decimal
    remaining_capacity: int
