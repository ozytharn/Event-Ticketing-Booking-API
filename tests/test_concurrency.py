import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="set TEST_DATABASE_URL to run PostgreSQL row-locking integration test",
)
def test_concurrent_last_seat_race():
    database_url = os.environ["TEST_DATABASE_URL"]
    admin_engine = create_engine(database_url)
    schema_name = f"booking_test_{uuid.uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema_name}"')

    engine = create_engine(
        database_url,
        connect_args={"options": f"-csearch_path={schema_name}"},
        pool_size=5,
        max_overflow=5,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            code = os.getenv("ORGANIZER_REGISTRATION_CODE", "test-organizer-code")
            organizer = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "race-organizer@example.com",
                    "full_name": "Race Organizer",
                    "password": "correct-horse-battery",
                    "role": "organizer",
                    "organizer_registration_code": code,
                },
            )
            assert organizer.status_code == 201
            organizer_token = client.post(
                "/api/v1/auth/login",
                data={
                    "username": "race-organizer@example.com",
                    "password": "correct-horse-battery",
                },
            ).json()["access_token"]
            organizer_headers = {"Authorization": f"Bearer {organizer_token}"}
            now = datetime.now(UTC)
            event = client.post(
                "/api/v1/events",
                headers=organizer_headers,
                json={
                    "title": "Last Seat Race",
                    "description": "One seat for two attendees",
                    "category": "Technology",
                    "city": "Bengaluru",
                    "venue": "Race Hall",
                    "starts_at": (now + timedelta(days=2)).isoformat(),
                    "ends_at": (now + timedelta(days=2, hours=1)).isoformat(),
                    "capacity": 1,
                    "price": 10,
                    "currency": "USD",
                    "status": "published",
                },
            )
            assert event.status_code == 201
            event_id = event.json()["id"]
            attendee_headers = []
            for suffix in ("a", "b"):
                email = f"race-attendee-{suffix}@example.com"
                response = client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": email,
                        "full_name": f"Attendee {suffix}",
                        "password": "correct-horse-battery",
                    },
                )
                assert response.status_code == 201
                token = client.post(
                    "/api/v1/auth/login",
                    data={"username": email, "password": "correct-horse-battery"},
                ).json()["access_token"]
                attendee_headers.append({"Authorization": f"Bearer {token}"})

            barrier = Barrier(2)

            def book(headers):
                barrier.wait(timeout=10)
                return client.post(f"/api/v1/bookings/events/{event_id}", headers=headers)

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(book, attendee_headers))

            assert sorted(response.status_code for response in results) == [201, 409]
            inventory = client.get(f"/api/v1/events/{event_id}")
            assert inventory.json()["booked_count"] == 1
            assert inventory.json()["available_seats"] == 0
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema_name}" CASCADE')
        admin_engine.dispose()
