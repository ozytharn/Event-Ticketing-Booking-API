from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.core.time import as_utc
from app.models.booking import Booking, BookingStatus, RefundStatus
from app.models.event import Event, EventStatus
from app.models.user import User


def get_booking_for_user(db: Session, user: User, booking_id: int) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise APIError(404, "booking_not_found", "Booking not found")
    if booking.attendee_id == user.id:
        return booking
    if user.role.value == "organizer":
        event = db.get(Event, booking.event_id)
        if event is not None and event.organizer_id == user.id:
            return booking
    raise APIError(404, "booking_not_found", "Booking not found")


def create_booking(db: Session, user: User, event_id: int, quantity: int = 1) -> Booking:
    try:
        event = db.scalar(select(Event).where(Event.id == event_id).with_for_update())
        if event is None:
            raise APIError(404, "event_not_found", "Event not found")
        if event.status != EventStatus.PUBLISHED:
            raise APIError(409, "event_unavailable", "This event is not open for booking")
        if as_utc(event.starts_at) <= datetime.now(UTC):
            raise APIError(409, "event_already_started", "Bookings are closed for started events")
        existing = db.scalar(
            select(Booking.id).where(Booking.event_id == event_id, Booking.attendee_id == user.id)
        )
        if existing is not None:
            raise APIError(409, "already_booked", "You already have a booking for this event")
        remaining = event.capacity - event.booked_count
        if quantity > remaining:
            raise APIError(
                409,
                "event_sold_out",
                f"Only {remaining} seat(s) remain for this event",
            )
        booking = Booking(
            event_id=event.id,
            attendee_id=user.id,
            quantity=quantity,
            unit_price=event.price,
            amount_paid=event.price * quantity,
            refund_status=RefundStatus.NOT_REQUIRED,
        )
        event.booked_count += quantity
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking
    except APIError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise APIError(409, "booking_conflict", "The booking could not be completed") from exc
    except Exception:
        db.rollback()
        raise


def update_booking_quantity(
    db: Session, user: User, booking_id: int, quantity: int
) -> Booking:
    try:
        current = db.get(Booking, booking_id)
        if current is None or current.attendee_id != user.id:
            raise APIError(404, "booking_not_found", "Booking not found")
        event = db.scalar(
            select(Event)
            .where(Event.id == current.event_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        booking = db.scalar(
            select(Booking)
            .where(Booking.id == booking_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if booking is None or booking.attendee_id != user.id:
            raise APIError(404, "booking_not_found", "Booking not found")
        if event is None:
            raise APIError(404, "event_not_found", "Event not found")
        if booking.status != BookingStatus.CONFIRMED:
            raise APIError(409, "booking_not_active", "Only confirmed bookings can be updated")
        if as_utc(event.starts_at) - datetime.now(UTC) < timedelta(hours=24):
            raise APIError(
                409,
                "booking_update_window_closed",
                "Bookings can only be updated at least 24 hours before the event starts",
            )
        if quantity < booking.quantity:
            raise APIError(
                409,
                "quantity_reduction_not_supported",
                "To reduce ticket quantity, cancel this booking and create a new booking",
            )
        additional = quantity - booking.quantity
        remaining = event.capacity - event.booked_count
        if additional > remaining:
            raise APIError(409, "event_sold_out", f"Only {remaining} additional seat(s) remain")
        event.booked_count += additional
        booking.quantity = quantity
        booking.amount_paid = booking.unit_price * quantity
        db.commit()
        db.refresh(booking)
        return booking
    except APIError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def cancel_booking(db: Session, user: User, booking_id: int) -> Booking:
    try:
        booking = db.get(Booking, booking_id)
        if booking is None or booking.attendee_id != user.id:
            raise APIError(404, "booking_not_found", "Booking not found")
        event = db.scalar(
            select(Event)
            .where(Event.id == booking.event_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        booking = db.scalar(
            select(Booking)
            .where(Booking.id == booking_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if booking is None or booking.attendee_id != user.id:
            raise APIError(404, "booking_not_found", "Booking not found")
        if booking.status != BookingStatus.CONFIRMED:
            raise APIError(409, "booking_not_active", "This booking has already been cancelled")
        if event is None:
            raise APIError(404, "event_not_found", "Event not found")
        if as_utc(event.starts_at) - datetime.now(UTC) < timedelta(hours=24):
            raise APIError(
                409,
                "cancellation_window_closed",
                "Bookings can only be cancelled at least 24 hours before the event starts",
            )
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = datetime.now(UTC)
        booking.refund_status = (
            RefundStatus.PENDING if booking.amount_paid > 0 else RefundStatus.NOT_REQUIRED
        )
        event.booked_count -= booking.quantity
        db.commit()
        db.refresh(booking)
        return booking
    except APIError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def mark_refunded(db: Session, booking: Booking) -> Booking:
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == booking.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if booking is None:
        raise APIError(404, "booking_not_found", "Booking not found")
    if booking.refund_status != RefundStatus.PENDING:
        raise APIError(409, "refund_not_pending", "This booking has no pending refund")
    booking.refund_status = RefundStatus.REFUNDED
    booking.refunded_at = datetime.now(UTC)
    db.commit()
    db.refresh(booking)
    return booking
