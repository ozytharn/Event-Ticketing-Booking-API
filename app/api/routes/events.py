from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DBSession, require_role
from app.core.errors import APIError
from app.core.time import as_utc
from app.models.booking import Booking, BookingStatus, RefundStatus
from app.models.event import Event, EventStatus
from app.models.user import User, UserRole
from app.schemas.booking import EventSalesSummary
from app.schemas.event import EventCreate, EventRead, EventUpdate

router = APIRouter(prefix="/events", tags=["events"])


def ensure_owner(event: Event, user: User) -> None:
    if event.organizer_id != user.id:
        raise APIError(404, "event_not_found", "Event not found")


@router.get("", response_model=list[EventRead])
def discover_events(
    db: DBSession,
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=100),
    city: str | None = Query(default=None, max_length=120),
    venue: str | None = Query(default=None, max_length=250),
    starts_after: datetime | None = None,
    starts_before: datetime | None = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[EventRead]:
    statement = select(Event).where(Event.status == EventStatus.PUBLISHED)
    if q:
        statement = statement.where(
            Event.title.ilike(f"%{q}%") | Event.description.ilike(f"%{q}%")
        )
    if category:
        statement = statement.where(Event.category.ilike(category))
    if city:
        statement = statement.where(Event.city.ilike(f"%{city}%"))
    if venue:
        statement = statement.where(Event.venue.ilike(f"%{venue}%"))
    if starts_after:
        statement = statement.where(Event.starts_at >= starts_after)
    if starts_before:
        statement = statement.where(Event.starts_at <= starts_before)
    if min_price is not None:
        statement = statement.where(Event.price >= min_price)
    if max_price is not None:
        statement = statement.where(Event.price <= max_price)
    events = db.scalars(
        statement.order_by(Event.starts_at, Event.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [EventRead.from_event(event) for event in events]


@router.get("/{event_id}/sales", response_model=EventSalesSummary)
def get_event_sales(event_id: int, user: CurrentUser, db: DBSession) -> EventSalesSummary:
    require_role(user, UserRole.ORGANIZER)
    event = db.get(Event, event_id)
    if event is None:
        raise APIError(404, "event_not_found", "Event not found")
    ensure_owner(event, user)
    tickets_sold, revenue = db.execute(
        select(
            func.coalesce(func.sum(Booking.quantity), 0),
            func.coalesce(func.sum(Booking.amount_paid), Decimal("0.00")),
        ).where(
            Booking.event_id == event_id,
            Booking.status == BookingStatus.CONFIRMED,
        )
    ).one()
    return EventSalesSummary(
        event_id=event.id,
        tickets_sold=tickets_sold,
        revenue=revenue,
        remaining_capacity=event.capacity - event.booked_count,
    )


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(payload: EventCreate, user: CurrentUser, db: DBSession) -> EventRead:
    require_role(user, UserRole.ORGANIZER)
    event = Event(organizer_id=user.id, **payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return EventRead.from_event(event)


@router.get("/mine", response_model=list[EventRead])
def list_my_events(
    user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[EventRead]:
    require_role(user, UserRole.ORGANIZER)
    events = db.scalars(
        select(Event)
        .where(Event.organizer_id == user.id)
        .order_by(Event.starts_at, Event.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [EventRead.from_event(event) for event in events]


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: int, db: DBSession) -> EventRead:
    event = db.get(Event, event_id)
    if event is None or event.status != EventStatus.PUBLISHED:
        raise APIError(404, "event_not_found", "Event not found")
    return EventRead.from_event(event)


@router.put("/{event_id}", response_model=EventRead)
def update_event(
    event_id: int, payload: EventUpdate, user: CurrentUser, db: DBSession
) -> EventRead:
    require_role(user, UserRole.ORGANIZER)
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise APIError(404, "event_not_found", "Event not found")
    ensure_owner(event, user)
    if event.status == EventStatus.CANCELLED:
        raise APIError(409, "event_cancelled", "Cancelled events cannot be edited")
    if as_utc(event.starts_at) <= datetime.now(UTC):
        raise APIError(409, "event_already_started", "Started events cannot be edited")
    if payload.capacity < event.booked_count:
        raise APIError(
            409,
            "capacity_below_bookings",
            "Capacity cannot be lower than the number of active bookings",
        )
    for field, value in payload.model_dump().items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return EventRead.from_event(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_event(event_id: int, user: CurrentUser, db: DBSession) -> None:
    require_role(user, UserRole.ORGANIZER)
    event = db.get(Event, event_id)
    if event is None:
        raise APIError(404, "event_not_found", "Event not found")
    ensure_owner(event, user)
    if event.status == EventStatus.CANCELLED:
        raise APIError(409, "event_already_cancelled", "This event is already cancelled")
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise APIError(404, "event_not_found", "Event not found")
    if event.status == EventStatus.CANCELLED:
        raise APIError(409, "event_already_cancelled", "This event is already cancelled")
    now = datetime.now(UTC)
    if as_utc(event.starts_at) <= now:
        raise APIError(409, "event_already_started", "Started events cannot be cancelled")
    bookings = db.scalars(
        select(Booking)
        .where(Booking.event_id == event_id, Booking.status == BookingStatus.CONFIRMED)
        .with_for_update()
    ).all()
    for booking in bookings:
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
        if booking.amount_paid > 0:
            booking.refund_status = RefundStatus.PENDING
    event.booked_count = 0
    event.status = EventStatus.CANCELLED
    db.commit()
