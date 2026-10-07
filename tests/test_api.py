from datetime import UTC, datetime, timedelta


def register(client, email, role="attendee", code=None):
    payload = {
        "email": email,
        "full_name": email.split("@")[0],
        "password": "correct-horse-battery",
        "role": role,
    }
    if code:
        payload["organizer_registration_code"] = code
    return client.post("/api/v1/auth/register", json=payload)


def login(client, email):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "correct-horse-battery"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_event(
    client,
    organizer_headers,
    *,
    capacity=1,
    price="25.00",
    category="Technology",
    city="Bengaluru",
    starts_in_hours=240,
):
    now = datetime.now(UTC)
    return client.post(
        "/api/v1/events",
        headers=organizer_headers,
        json={
            "title": "Concurrency Summit",
            "description": "A systems engineering event",
            "category": category,
            "city": city,
            "venue": "Hall A",
            "starts_at": (now + timedelta(hours=starts_in_hours)).isoformat(),
            "ends_at": (now + timedelta(hours=starts_in_hours + 2)).isoformat(),
            "capacity": capacity,
            "price": price,
            "currency": "USD",
            "status": "published",
        },
    )


def test_auth_rbac_booking_cancellation_and_refund_lifecycle(client):
    openapi = client.get("/openapi.json").json()
    assert openapi["info"]["title"] == "Event Booking API"
    assert "/api/v1/bookings/events/{event_id}" in openapi["paths"]

    denied = register(client, "organizer@example.com", role="organizer", code="wrong-code")
    assert denied.status_code == 403
    organizer = register(
        client, "organizer@example.com", role="organizer", code="test-organizer-code"
    )
    assert organizer.status_code == 201
    organizer_headers = login(client, "organizer@example.com")

    attendee = register(client, "attendee@example.com")
    assert attendee.status_code == 201
    attendee_headers = login(client, "attendee@example.com")
    assert client.get("/api/v1/auth/me", headers=attendee_headers).json()["role"] == "attendee"

    event_response = create_event(client, organizer_headers)
    assert event_response.status_code == 201
    event = event_response.json()
    assert event["available_seats"] == 1
    forbidden_event = create_event(client, attendee_headers)
    assert forbidden_event.status_code == 403

    booking_response = client.post(
        f"/api/v1/bookings/events/{event['id']}", headers=attendee_headers
    )
    assert booking_response.status_code == 201
    booking = booking_response.json()
    assert booking["status"] == "confirmed"
    assert booking["refund_status"] == "not_required"
    assert client.get(f"/api/v1/events/{event['id']}").json()["available_seats"] == 0

    second_attendee = register(client, "second@example.com")
    assert second_attendee.status_code == 201
    second_headers = login(client, "second@example.com")
    sold_out = client.post(f"/api/v1/bookings/events/{event['id']}", headers=second_headers)
    assert sold_out.status_code == 409
    assert sold_out.json()["error"]["code"] == "event_sold_out"

    cancelled = client.delete(f"/api/v1/bookings/{booking['id']}", headers=attendee_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["refund_status"] == "pending"
    assert client.get(f"/api/v1/events/{event['id']}").json()["available_seats"] == 1

    refunded = client.post(f"/api/v1/bookings/{booking['id']}/refund", headers=organizer_headers)
    assert refunded.status_code == 200
    assert refunded.json()["refund_status"] == "refunded"
    assert refunded.json()["refunded_at"] is not None


def test_event_discovery_ownership_and_structured_validation(client):
    unauthenticated = client.get("/api/v1/bookings/mine")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "http_error"

    register(client, "owner@example.com", role="organizer", code="test-organizer-code")
    owner_headers = login(client, "owner@example.com")
    register(client, "other@example.com", role="organizer", code="test-organizer-code")
    other_headers = login(client, "other@example.com")
    event_response = create_event(client, owner_headers, capacity=3, price="0.00")
    event_id = event_response.json()["id"]

    assert len(client.get("/api/v1/events", params={"q": "Concurrency"}).json()) == 1
    assert client.get("/api/v1/events", params={"venue": "missing"}).json() == []
    assert (
        client.put(f"/api/v1/events/{event_id}", headers=other_headers, json={}).json()["error"][
            "code"
        ]
        == "validation_error"
    )
    not_owner = client.delete(f"/api/v1/events/{event_id}", headers=other_headers)
    assert not_owner.status_code == 404
    assert not_owner.json()["error"]["code"] == "event_not_found"

    bad_event = client.post(
        "/api/v1/events",
        headers=owner_headers,
        json={
            "title": "Bad time",
            "description": "Bad",
            "category": "Technology",
            "city": "Bengaluru",
            "venue": "Here",
            "starts_at": "2030-01-02T00:00:00",
            "ends_at": "2030-01-01T00:00:00",
            "capacity": 1,
            "price": 0,
            "currency": "USD",
            "status": "published",
        },
    )
    assert bad_event.status_code == 422
    assert bad_event.json()["error"]["code"] == "validation_error"

    attendee = register(client, "free-attendee@example.com")
    assert attendee.status_code == 201
    attendee_headers = login(client, "free-attendee@example.com")
    booking = client.post(f"/api/v1/bookings/events/{event_id}", headers=attendee_headers)
    cancellation = client.delete(
        f"/api/v1/bookings/{booking.json()['id']}", headers=attendee_headers
    )
    assert cancellation.json()["refund_status"] == "not_required"


def test_organizer_event_cancellation_queues_refunds(client):
    register(client, "cancel-owner@example.com", role="organizer", code="test-organizer-code")
    owner_headers = login(client, "cancel-owner@example.com")
    event = create_event(client, owner_headers, capacity=2, price="12.50").json()
    register(client, "event-cancel-attendee@example.com")
    attendee_headers = login(client, "event-cancel-attendee@example.com")
    booking = client.post(f"/api/v1/bookings/events/{event['id']}", headers=attendee_headers).json()

    cancelled = client.delete(f"/api/v1/events/{event['id']}", headers=owner_headers)
    assert cancelled.status_code == 204
    assert client.get(f"/api/v1/events/{event['id']}").status_code == 404
    updated_booking = client.get("/api/v1/bookings/mine", headers=attendee_headers).json()[0]
    assert updated_booking["id"] == booking["id"]
    assert updated_booking["status"] == "cancelled"
    assert updated_booking["refund_status"] == "pending"


def test_event_filters_multiple_tickets_sales_and_cancellation_window(client):
    register(client, "filters-owner@example.com", role="organizer", code="test-organizer-code")
    organizer_headers = login(client, "filters-owner@example.com")
    event = create_event(
        client,
        organizer_headers,
        capacity=4,
        price="20.00",
        category="Music",
        city="Toronto",
    )
    event_payload = event.json()

    filtered = client.get(
        "/api/v1/events",
        params={
            "category": "music",
            "city": "toronto",
            "min_price": "15",
            "max_price": "25",
            "page": 1,
            "page_size": 5,
        },
    )
    assert [item["id"] for item in filtered.json()] == [event_payload["id"]]
    paginated = client.get("/api/v1/events", params={"page": 1, "page_size": 1})
    assert paginated.status_code == 200
    assert len(paginated.json()) == 1
    my_events = client.get(
        "/api/v1/events/mine",
        headers=organizer_headers,
        params={"page": 1, "page_size": 1},
    )
    assert my_events.status_code == 200
    assert len(my_events.json()) == 1

    register(client, "quantity-attendee@example.com")
    attendee_headers = login(client, "quantity-attendee@example.com")
    booking = client.post(
        f"/api/v1/bookings/events/{event_payload['id']}",
        headers=attendee_headers,
        json={"quantity": 2},
    )
    assert booking.status_code == 201
    assert booking.json()["quantity"] == 2
    assert booking.json()["amount_paid"] == "40.00"
    detail = client.get(f"/api/v1/events/{event_payload['id']}").json()
    assert detail["booked_count"] == 2
    assert detail["available_seats"] == 2

    summary = client.get(
        f"/api/v1/events/{event_payload['id']}/sales", headers=organizer_headers
    )
    assert summary.status_code == 200
    assert summary.json() == {
        "event_id": event_payload["id"],
        "tickets_sold": 2,
        "revenue": "40.00",
        "remaining_capacity": 2,
    }

    soon = create_event(
        client, organizer_headers, capacity=1, price="10.00", starts_in_hours=12
    ).json()
    late_booking = client.post(
        f"/api/v1/bookings/events/{soon['id']}", headers=attendee_headers
    )
    assert late_booking.status_code == 201
    cancellation = client.delete(
        f"/api/v1/bookings/{late_booking.json()['id']}", headers=attendee_headers
    )
    assert cancellation.status_code == 409
    assert cancellation.json()["error"]["code"] == "cancellation_window_closed"


def test_user_self_service_crud_and_token_deactivation(client):
    created = register(client, "profile@example.com")
    assert created.status_code == 201
    user_id = created.json()["id"]
    headers = login(client, "profile@example.com")

    assert client.get("/api/v1/users/me", headers=headers).json()["id"] == user_id
    assert client.get(f"/api/v1/users/{user_id}", headers=headers).status_code == 200
    forbidden = client.get(f"/api/v1/users/{user_id + 100}", headers=headers)
    assert forbidden.status_code == 404

    bad_password = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"current_password": "wrong-password", "new_password": "new-password-123"},
    )
    assert bad_password.status_code == 403
    role_change = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"full_name": "Attempted Escalation", "role": "organizer"},
    )
    assert role_change.status_code == 422

    updated = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={
            "email": "profile-updated@example.com",
            "full_name": "Updated Profile",
            "current_password": "correct-horse-battery",
            "new_password": "new-password-123",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["email"] == "profile-updated@example.com"
    assert updated.json()["full_name"] == "Updated Profile"
    assert client.post(
        "/api/v1/auth/login",
        data={"username": "profile@example.com", "password": "correct-horse-battery"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        data={"username": "profile-updated@example.com", "password": "new-password-123"},
    ).status_code == 200

    deleted = client.delete("/api/v1/users/me", headers=headers)
    assert deleted.status_code == 204
    assert client.get("/api/v1/users/me", headers=headers).status_code == 401


def test_booking_read_and_quantity_update(client):
    register(
        client, "booking-update-owner@example.com", role="organizer", code="test-organizer-code"
    )
    organizer_headers = login(client, "booking-update-owner@example.com")
    event = create_event(client, organizer_headers, capacity=3, price="15.00").json()
    register(client, "booking-update-attendee@example.com")
    attendee_headers = login(client, "booking-update-attendee@example.com")
    booking = client.post(
        f"/api/v1/bookings/events/{event['id']}",
        headers=attendee_headers,
        json={"quantity": 1},
    ).json()

    read = client.get(f"/api/v1/bookings/{booking['id']}", headers=attendee_headers)
    assert read.status_code == 200
    assert read.json()["unit_price"] == "15.00"

    updated = client.put(
        f"/api/v1/bookings/{booking['id']}",
        headers=attendee_headers,
        json={"quantity": 2},
    )
    assert updated.status_code == 200
    assert updated.json()["quantity"] == 2
    assert updated.json()["amount_paid"] == "30.00"
    assert client.get(f"/api/v1/events/{event['id']}").json()["booked_count"] == 2

    decrease = client.put(
        f"/api/v1/bookings/{booking['id']}",
        headers=attendee_headers,
        json={"quantity": 1},
    )
    assert decrease.status_code == 409
    assert decrease.json()["error"]["code"] == "quantity_reduction_not_supported"

    register(client, "booking-outsider@example.com")
    outsider_headers = login(client, "booking-outsider@example.com")
    outsider_read = client.get(
        f"/api/v1/bookings/{booking['id']}", headers=outsider_headers
    )
    assert outsider_read.status_code == 404
    assert client.get(
        f"/api/v1/bookings/{booking['id']}", headers=organizer_headers
    ).status_code == 200
    organizer_page = client.get(
        f"/api/v1/bookings/events/{event['id']}/organizer",
        headers=organizer_headers,
        params={"page": 1, "page_size": 1},
    )
    assert organizer_page.status_code == 200
    assert len(organizer_page.json()) == 1
