from typing import Annotated

from fastapi import APIRouter, Body, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, require_role
from app.core.errors import APIError
from app.models.booking import Booking
from app.models.event import Event
from app.models.user import UserRole
from app.schemas.booking import BookingCreate, BookingRead, BookingUpdate
from app.services.bookings import (
    cancel_booking,
    create_booking,
    get_booking_for_user,
    mark_refunded,
    update_booking_quantity,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/events/{event_id}", response_model=BookingRead, status_code=201)
def book_event(
    event_id: int,
    user: CurrentUser,
    db: DBSession,
    payload: Annotated[BookingCreate | None, Body()] = None,
) -> Booking:
    require_role(user, UserRole.ATTENDEE)
    return create_booking(db, user, event_id, payload.quantity if payload else 1)


@router.get("/mine", response_model=list[BookingRead])
def list_my_bookings(
    user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[Booking]:
    require_role(user, UserRole.ATTENDEE)
    return db.scalars(
        select(Booking)
        .where(Booking.attendee_id == user.id)
        .order_by(Booking.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()


@router.get("/{booking_id}", response_model=BookingRead)
def read_booking(booking_id: int, user: CurrentUser, db: DBSession) -> Booking:
    return get_booking_for_user(db, user, booking_id)


@router.put("/{booking_id}", response_model=BookingRead)
def update_my_booking(
    booking_id: int, payload: BookingUpdate, user: CurrentUser, db: DBSession
) -> Booking:
    require_role(user, UserRole.ATTENDEE)
    return update_booking_quantity(db, user, booking_id, payload.quantity)


@router.delete("/{booking_id}", response_model=BookingRead)
def cancel_my_booking(booking_id: int, user: CurrentUser, db: DBSession) -> Booking:
    require_role(user, UserRole.ATTENDEE)
    return cancel_booking(db, user, booking_id)


@router.get("/events/{event_id}/organizer", response_model=list[BookingRead])
def list_event_bookings(
    event_id: int,
    user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[Booking]:
    require_role(user, UserRole.ORGANIZER)
    event = db.get(Event, event_id)
    if event is None or event.organizer_id != user.id:
        raise APIError(404, "event_not_found", "Event not found")
    return db.scalars(
        select(Booking)
        .where(Booking.event_id == event_id)
        .order_by(Booking.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()


@router.post("/{booking_id}/refund", response_model=BookingRead)
def complete_refund(booking_id: int, user: CurrentUser, db: DBSession) -> Booking:
    require_role(user, UserRole.ORGANIZER)
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise APIError(404, "booking_not_found", "Booking not found")
    event = db.get(Event, booking.event_id)
    if event is None or event.organizer_id != user.id:
        raise APIError(404, "booking_not_found", "Booking not found")
    return mark_refunded(db, booking)
