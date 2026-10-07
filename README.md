# Event Booking API

A FastAPI and PostgreSQL service for event discovery, organizer-managed events, authenticated bookings, and cancellation/refund tracking. PostgreSQL row locks serialize bookings per event so requests competing for the last seat cannot overbook.

## Run with Docker Compose

1. Set a strong signing key (at least 32 characters) and optionally an organizer registration code.
2. Start the API and database:

```powershell
$env:JWT_SECRET_KEY = "replace-this-with-a-long-random-secret-value"
$env:ORGANIZER_REGISTRATION_CODE = "your-organizer-invite-code"
docker compose up --build
```

The API is at `http://localhost:8000`. Swagger UI and the OpenAPI document are available at `/docs` and `/openapi.json`; `/health` is a liveness endpoint. Compose applies Alembic migrations before starting Uvicorn. PostgreSQL is bound to `127.0.0.1:5433` for local tools and race-test access; the API connects to it over the private Compose network.

## Run locally

Requires Python 3.11+ and PostgreSQL. Create a virtual environment, install the project, and configure `.env` from `.env.example`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

Set `JWT_SECRET_KEY` to a random value of at least 32 characters. Set `ORGANIZER_REGISTRATION_CODE` to enable organizer signup; absent a code, registration is attendee-only. The organizer code is supplied in the registration body only when registering an organizer.

## Authentication and roles

Register at `POST /api/v1/auth/register`, then exchange email and password as OAuth2 form fields at `POST /api/v1/auth/login`. Send the returned bearer token as `Authorization: Bearer <token>`. `GET /api/v1/auth/me` returns the authenticated profile. Public role escalation is blocked: organizer registration requires the configured invite code.

## API overview

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Public | Create an attendee or invite-code-authorized organizer account. |
| `POST` | `/api/v1/auth/login` | Public | Authenticate and obtain a JWT access token. |
| `GET` | `/api/v1/users/me` | Authenticated user | Read own profile. |
| `GET` | `/api/v1/users/{user_id}` | Same user only | Read own profile by ID; other users are hidden. |
| `PATCH` | `/api/v1/users/me` | Authenticated user | Update own email/name or change password using the current password. Role changes are prohibited. |
| `DELETE` | `/api/v1/users/me` | Authenticated user | Deactivate and anonymize the account while preserving related events/bookings. |
| `GET` | `/api/v1/events` | Public | Discover published events. Supports `q`, `category`, `city`, `venue`, `starts_after`, `starts_before`, `min_price`, `max_price`, `page`, and `page_size`. |
| `GET` | `/api/v1/events/{event_id}` | Public | Read a published event and current availability. |
| `POST` | `/api/v1/events` | Organizer | Create an event. |
| `GET` | `/api/v1/events/mine` | Organizer | Paginated list of the organizer's events (`page`, `page_size`). |
| `PUT` | `/api/v1/events/{event_id}` | Owner organizer | Replace event details; capacity cannot be lowered below active bookings. |
| `DELETE` | `/api/v1/events/{event_id}` | Owner organizer | Cancel an event (soft delete), cancel active bookings, and queue paid refunds. |
| `GET` | `/api/v1/events/{event_id}/sales` | Owner organizer | View confirmed ticket sales, revenue, and remaining capacity. |
| `POST` | `/api/v1/bookings/events/{event_id}` | Attendee | Reserve one or more seats with `{"quantity":2}`. A booking cannot be duplicated for the same attendee/event. |
| `GET` | `/api/v1/bookings/mine` | Attendee | Paginated list of own bookings (`page`, `page_size`). |
| `GET` | `/api/v1/bookings/{booking_id}` | Booking attendee or event owner | Read one booking, subject to ownership checks. |
| `PUT` | `/api/v1/bookings/{booking_id}` | Booking attendee | Increase ticket quantity transactionally before the 24-hour cutoff. To reduce quantity, cancel and rebook. |
| `DELETE` | `/api/v1/bookings/{booking_id}` | Booking attendee | Cancel and release the seat. Paid bookings enter `pending` refund status. |
| `GET` | `/api/v1/bookings/events/{event_id}/organizer` | Event owner | Paginated event bookings (`page`, `page_size`). |
| `POST` | `/api/v1/bookings/{booking_id}/refund` | Event owner | Mark a pending refund as completed. |

Booking and cancellation update inventory and booking state in a single database transaction. Booking locks the event row with `SELECT ... FOR UPDATE`; the database also enforces seat-count checks and one booking per attendee/event. Each booking records its ticket quantity and total amount. Attendees may cancel at least 24 hours before the event starts; later cancellation attempts are rejected. Started events cannot be edited, cancelled, or booked. A paid booking records the event's listed amount, and attendee or organizer event cancellation creates a pending refund record; actual payment processing is deliberately outside this API.

All application errors use the JSON shape `{"error":{"code":"...","message":"...","details":...}}`. Validation errors return `422` with field details. The OpenAPI schema documents the endpoints and bearer authentication.

User records are self-managed: registration creates a user, and an authenticated user can read/update/deactivate only their own account. Profile updates cannot change roles; password changes require the current password. Deactivation anonymizes personal profile fields and invalidates access tokens but preserves referenced events and booking records. There is intentionally no global user directory or administrator role.

## Tests

```powershell
python -m pip install -e ".[dev]"
pytest
```

The functional suite uses an isolated SQLite database. The concurrent last-seat test requires a disposable PostgreSQL database URL in `TEST_DATABASE_URL`; it creates and drops a uniquely named schema in that database:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://events:events@127.0.0.1:5433/events"
pytest -k concurrent_last_seat
```

The PostgreSQL test confirms exactly one of two simultaneous requests succeeds when a single seat remains.

## Request/response examples

Register an attendee:

```http
POST /api/v1/auth/register
Content-Type: application/json

{"email":"attendee@example.com","full_name":"Alex Attendee","password":"a-long-password","role":"attendee"}
```

Registering an organizer uses `"role":"organizer"` and includes the configured `organizer_registration_code`. Login uses OAuth2 form fields `username` (email) and `password`; use the resulting token as `Authorization: Bearer <access_token>`.

Create a published event as an organizer:

```json
{
  "title": "Backend Workshop",
  "description": "A hands-on API workshop",
  "category": "Workshop",
  "city": "Bengaluru",
  "venue": "Hall A",
  "starts_at": "2026-12-10T10:00:00+00:00",
  "ends_at": "2026-12-10T12:00:00+00:00",
  "capacity": 80,
  "price": "25.00",
  "currency": "USD",
  "status": "published"
}
```

Reserve two tickets as an attendee:

```http
POST /api/v1/bookings/events/42
Authorization: Bearer <access_token>
Content-Type: application/json

{"quantity":2}
```

Example booking response:

```json
{
  "id": 105,
  "event_id": 42,
  "attendee_id": 9,
  "quantity": 2,
  "unit_price": "25.00",
  "status": "confirmed",
  "amount_paid": "50.00",
  "refund_status": "not_required"
}
```

All generated schemas and complete operation details are available at `/docs` and `/openapi.json`. List routes accept `page` (starts at 1) and `page_size` (1-100).

## Data model

- `users`: unique normalized email, password hash, attendee/organizer role, activation flag, creation timestamp.
- `events`: organizer foreign key, title, description, category, city, venue, timezone-aware start/end, status, capacity/booked count, price/currency.
- `bookings`: event and attendee foreign keys, quantity, ticket unit-price snapshot, total amount, booking/refund status, timestamps.
- One user has many bookings; an organizer has many events; an event has many bookings. Unique `(event_id, attendee_id)` prevents duplicate bookings.
- Indexes cover user email, event organizer/title/category/city/start time, and booking event/attendee. Check constraints enforce positive capacity/quantity, bounded seat count, and nonnegative price.
- Foreign keys use `RESTRICT` to preserve financial and event history. Account deactivation is soft/anonymizing; event cancellation is a status transition that preserves bookings and queues refunds.

## Error codes

| HTTP | Code | Meaning |
| --- | --- | --- |
| `401` | `invalid_credentials`, `invalid_token`, `http_error` | Authentication is missing or invalid. |
| `403` | `forbidden`, `organizer_registration_denied`, `current_password_incorrect` | Authenticated caller lacks the required permission or credential. |
| `404` | `event_not_found`, `booking_not_found`, `user_not_found` | Resource does not exist or is not visible to this caller. |
| `409` | `email_already_registered`, `event_unavailable`, `event_already_started`, `event_sold_out`, `already_booked`, `booking_conflict`, `booking_not_active`, `booking_update_window_closed`, `quantity_reduction_not_supported`, `capacity_below_bookings`, `cancellation_window_closed`, `refund_not_pending` | Request conflicts with current resource state, ownership, lifecycle, or capacity. |
| `422` | `validation_error` | Payload/query validation failed; `details` identifies invalid fields. |
| `500` | `internal_server_error` | Unexpected server-side failure; details are not exposed. |

## Security notes

- Passwords are hashed with the recommended Argon2 configuration from `pwdlib`; plaintext passwords are never stored.
- JWTs use a configurable signing secret and expire after the configured access-token lifetime. Access tokens are invalidated when an account is deactivated.
- Set `JWT_SECRET_KEY` and `ORGANIZER_REGISTRATION_CODE` through environment/secret management; do not commit `.env` or production secrets. The Compose database credentials are development-only and must be replaced for deployment.
- Organizer registration is invite-code gated; users cannot update their own role. User profile operations are self-only, organizer event/booking access is owner-scoped, and attendee booking operations are attendee-scoped.
- The API does not process payment transactions or send real refunds; refund statuses model the workflow for an integrated payment provider.

## Test cases and expected outcomes

| Scenario | Expected result |
| --- | --- |
| Register and authenticate valid attendee/organizer | Registration `201`; login `200`; JWT protects caller-specific operations. |
| Invalid role, payload, timezone, or event interval | `422` structured `validation_error`. |
| Attendee attempts organizer-only event creation | `403 forbidden`. |
| Organizer attempts to modify another organizer's event | `404 event_not_found` to avoid leaking resource existence. |
| Attendee buys tickets within remaining capacity | `201 confirmed`; `booked_count` increases by requested quantity and amount is unit price times quantity. |
| Quantity exceeds remaining seats | `409 event_sold_out`; inventory is unchanged. |
| Attendee cancels fewer than 24 hours before start | `409 cancellation_window_closed`; booking and inventory are unchanged. |
| Organizer cancels a future event with paid bookings | Event becomes cancelled; affected bookings become cancelled with refund status pending. |
| Two attendees concurrently request a single remaining seat | Exactly one `201`, one `409`; final booked count remains at capacity. |

Run `python -m pytest -q` for the functional tests. Set `TEST_DATABASE_URL` to PostgreSQL and run the same command to include the concurrent race test; the task was verified with all seven tests passing.

## Configuration

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL; production deployment expects PostgreSQL via `postgresql+psycopg://...`. |
| `JWT_SECRET_KEY` | Required, minimum 32-character JWT signing key. |
| `JWT_ALGORITHM` | JWT algorithm (default `HS256`). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Bearer token lifetime (default `30`). |
| `ORGANIZER_REGISTRATION_CODE` | Optional invite code; organizer self-registration is disabled if unset. |
