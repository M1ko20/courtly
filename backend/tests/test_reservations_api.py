from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from support import default_venue_id, make_venue_manager

from reservations.main import app
from reservations.models import Court, SportType

PRAGUE = ZoneInfo("Europe/Prague")

# Booking rules require a start time within [15 min, 14 days) from "now" —
# tests book a few days out so they stay valid regardless of when they run.
TEST_DAYS_AHEAD = 3


def future_date():
    return (datetime.now(PRAGUE) + timedelta(days=TEST_DAYS_AHEAD)).date()


def at(hour: int, minute: int = 0) -> str:
    day = future_date()
    return datetime(
        day.year, day.month, day.day, hour, minute, tzinfo=PRAGUE
    ).isoformat()


def register_and_login(client: TestClient, email: str) -> str:
    client.post(
        "/auth/register",
        json={"name": "Player", "email": email, "password": "supersecret"},
    )
    response = client.post(
        "/auth/login", json={"email": email, "password": "supersecret"}
    )
    return response.json()["access_token"]


def seed_court(session_factory: sessionmaker, name: str = "Tennis 1") -> str:
    with session_factory() as session:
        court = Court(venue_id=default_venue_id(session), name=name, sport_type=SportType.TENNIS, indoor=False)
        session.add(court)
        session.commit()
        return str(court.id)


def test_create_reservation_success(session_factory: sessionmaker) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "dana@example.com")

    response = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["hold_expires_at"] is not None
    assert body["court"]["id"] == court_id


def test_create_reservation_rejects_bad_slot_length(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "erin@example.com")

    response = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(18, 45)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_create_reservation_rejects_outside_opening_hours(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "irene@example.com")

    response = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(21, 30), "end_time": at(23)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_create_reservation_uses_venue_local_time_not_utc(
    session_factory: sessionmaker,
) -> None:
    """BR-04 is checked in Europe/Prague: opening (07:00 local) sent as its
    UTC instant must be accepted, one slot earlier must not. The UTC times are
    derived from local time for the day under test, so the oracle holds in
    both CET and CEST (a fixed 05:00Z broke when the date crossed into CET)."""
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "kate@example.com")
    day = future_date()
    utc = ZoneInfo("UTC")

    def utc_slot(hour: int) -> dict[str, str]:
        start = datetime(day.year, day.month, day.day, hour, tzinfo=PRAGUE)
        return {
            "court_id": court_id,
            "start_time": start.astimezone(utc).isoformat().replace("+00:00", "Z"),
            "end_time": (start + timedelta(hours=1))
            .astimezone(utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }

    headers = {"Authorization": f"Bearer {token}"}
    assert (
        client.post("/reservations", json=utc_slot(6), headers=headers).status_code
        == 422
    )
    assert (
        client.post("/reservations", json=utc_slot(7), headers=headers).status_code
        == 201
    )


def test_create_reservation_requires_auth(session_factory: sessionmaker) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)

    response = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
    )

    assert response.status_code == 401


def test_create_reservation_rejects_too_soon(session_factory: sessionmaker) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "quinn@example.com")
    # A fixed midday slot yesterday: always in the past (so always "too soon"
    # regardless of lead time) while still shaped like a valid slot, so this
    # exercises the lead-time rule specifically rather than opening hours.
    yesterday_noon = (datetime.now(PRAGUE) - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )

    response = client.post(
        "/reservations",
        json={
            "court_id": court_id,
            "start_time": yesterday_noon.isoformat(),
            "end_time": (yesterday_noon + timedelta(hours=1)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409


def test_create_reservation_rejects_too_far_ahead(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "riley@example.com")
    far = datetime.now(PRAGUE).replace(
        hour=18, minute=0, second=0, microsecond=0
    ) + timedelta(days=30)

    response = client.post(
        "/reservations",
        json={
            "court_id": court_id,
            "start_time": far.isoformat(),
            "end_time": (far + timedelta(hours=1)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409


def test_active_reservation_limit_enforced_for_players(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "sam@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    for hour in (10, 12, 14):
        response = client.post(
            "/reservations",
            json={
                "court_id": court_id,
                "start_time": at(hour),
                "end_time": at(hour + 1),
            },
            headers=headers,
        )
        assert response.status_code == 201

    response = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(16), "end_time": at(17)},
        headers=headers,
    )
    assert response.status_code == 409


def test_second_hold_on_same_slot_is_rejected(session_factory: sessionmaker) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token_a = register_and_login(client, "taylor@example.com")
    token_b = register_and_login(client, "uma@example.com")

    first = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert first.status_code == 201

    second = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert second.status_code == 409


def test_confirm_then_cancel_reservation(session_factory: sessionmaker) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "frank@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers=headers,
    ).json()

    confirmed = client.post(f"/reservations/{created['id']}/confirm", headers=headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"
    assert confirmed.json()["hold_expires_at"] is None

    cancelled = client.post(f"/reservations/{created['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"


def test_cannot_cancel_already_cancelled_reservation(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "vera@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers=headers,
    ).json()
    client.post(f"/reservations/{created['id']}/cancel", headers=headers)

    response = client.post(f"/reservations/{created['id']}/cancel", headers=headers)

    assert response.status_code == 409


def test_check_in_requires_confirmed_first(session_factory: sessionmaker) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "walt@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers=headers,
    ).json()

    too_early = client.post(f"/reservations/{created['id']}/check-in", headers=headers)
    assert too_early.status_code == 409

    client.post(f"/reservations/{created['id']}/confirm", headers=headers)
    checked_in = client.post(f"/reservations/{created['id']}/check-in", headers=headers)
    assert checked_in.status_code == 200
    assert checked_in.json()["status"] == "CHECKED_IN"


def test_reschedule_moves_reservation_and_frees_old_slot(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "xena@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers=headers,
    ).json()

    response = client.patch(
        f"/reservations/{created['id']}/reschedule",
        json={"start_time": at(20), "end_time": at(21)},
        headers=headers,
    )

    assert response.status_code == 200
    assert datetime.fromisoformat(
        response.json()["start_time"]
    ) == datetime.fromisoformat(at(20))

    history = client.get(f"/reservations/{created['id']}/history", headers=headers)
    events = history.json()
    event_types = [event["event_type"] for event in events]
    assert "TIME_CHANGED" in event_types
    time_changed = next(e for e in events if e["event_type"] == "TIME_CHANGED")
    assert time_changed["actor"]["email"] == "xena@example.com"

    # The original 18:00 slot should be free again.
    other_token = register_and_login(client, "yusuf@example.com")
    reclaim = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert reclaim.status_code == 201


def test_cannot_confirm_someone_elses_reservation(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    owner_token = register_and_login(client, "gina@example.com")
    other_token = register_and_login(client, "hank@example.com")
    created = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers={"Authorization": f"Bearer {owner_token}"},
    ).json()

    response = client.post(
        f"/reservations/{created['id']}/confirm",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 403


def test_list_my_reservations_only_returns_own(session_factory: sessionmaker) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token_a = register_and_login(client, "iris@example.com")
    token_b = register_and_login(client, "jack@example.com")
    client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    response = client.get(
        "/reservations", headers={"Authorization": f"Bearer {token_b}"}
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_courts_returns_active_courts(session_factory: sessionmaker) -> None:
    client = TestClient(app)
    seed_court(session_factory, name="Badminton 1")

    response = client.get("/courts")

    assert response.status_code == 200
    names = [court["name"] for court in response.json()]
    assert "Badminton 1" in names


def test_non_manager_cannot_list_all_reservations(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    token = register_and_login(client, "logan@example.com")

    response = client.get(
        "/reservations/admin", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_manager_lists_all_reservations_with_booker(
    session_factory: sessionmaker,
) -> None:
    from reservations.models import User

    client = TestClient(app)
    court_id = seed_court(session_factory)
    player_token = register_and_login(client, "mia@example.com")
    created = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers={"Authorization": f"Bearer {player_token}"},
    ).json()
    register_and_login(client, "guest-of-mia@example.com")
    client.post(
        f"/reservations/{created['id']}/guests",
        json={"email": "guest-of-mia@example.com"},
        headers={"Authorization": f"Bearer {player_token}"},
    )

    manager_token = register_and_login(client, "noah-manager@example.com")
    with session_factory() as session:
        manager = session.query(User).filter_by(email="noah-manager@example.com").one()
        make_venue_manager(session, manager)
        session.commit()

    response = client.get(
        "/reservations/admin", headers={"Authorization": f"Bearer {manager_token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["user"]["email"] == "mia@example.com"
    assert [g["user"]["email"] for g in body[0]["guests"]] == [
        "guest-of-mia@example.com"
    ]


def test_list_my_reservations_respects_limit_and_offset(
    session_factory: sessionmaker,
) -> None:
    from reservations.models import Reservation, ReservationStatus, User

    client = TestClient(app)
    token = register_and_login(client, "paige@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    with session_factory() as session:
        user = session.query(User).filter_by(email="paige@example.com").one()
        for i in range(5):
            court = Court(venue_id=default_venue_id(session), 
                name=f"Pagination Court {i}", sport_type=SportType.TENNIS, indoor=False
            )
            session.add(court)
            session.flush()
            start = datetime(
                future_date().year,
                future_date().month,
                future_date().day,
                8 + i,
                tzinfo=PRAGUE,
            )
            session.add(
                Reservation(
                    court_id=court.id,
                    user_id=user.id,
                    start_time=start,
                    end_time=start + timedelta(hours=1),
                    status=ReservationStatus.CONFIRMED,
                )
            )
        session.commit()

    first_page = client.get(
        "/reservations", params={"limit": 2, "offset": 0}, headers=headers
    )
    assert first_page.status_code == 200
    assert len(first_page.json()) == 2

    second_page = client.get(
        "/reservations", params={"limit": 2, "offset": 2}, headers=headers
    )
    assert len(second_page.json()) == 2

    first_ids = {r["id"] for r in first_page.json()}
    second_ids = {r["id"] for r in second_page.json()}
    assert first_ids.isdisjoint(second_ids)

    all_default = client.get("/reservations", headers=headers)
    assert len(all_default.json()) == 5


def test_admin_reservations_list_respects_limit_and_offset(
    session_factory: sessionmaker,
) -> None:
    from reservations.models import Reservation, ReservationStatus, User

    client = TestClient(app)
    register_and_login(client, "quinn@example.com")

    with session_factory() as session:
        user = session.query(User).filter_by(email="quinn@example.com").one()
        for i in range(4):
            court = Court(venue_id=default_venue_id(session), 
                name=f"Admin Pagination Court {i}",
                sport_type=SportType.TENNIS,
                indoor=False,
            )
            session.add(court)
            session.flush()
            start = datetime(
                future_date().year,
                future_date().month,
                future_date().day,
                8 + i,
                tzinfo=PRAGUE,
            )
            session.add(
                Reservation(
                    court_id=court.id,
                    user_id=user.id,
                    start_time=start,
                    end_time=start + timedelta(hours=1),
                    status=ReservationStatus.CONFIRMED,
                )
            )
        session.commit()

    manager_token = register_and_login(client, "quinn-manager@example.com")
    with session_factory() as session:
        manager = session.query(User).filter_by(email="quinn-manager@example.com").one()
        make_venue_manager(session, manager)
        session.commit()

    headers = {"Authorization": f"Bearer {manager_token}"}
    first_page = client.get(
        "/reservations/admin", params={"limit": 3, "offset": 0}, headers=headers
    )
    assert len(first_page.json()) == 3

    second_page = client.get(
        "/reservations/admin", params={"limit": 3, "offset": 3}, headers=headers
    )
    assert len(second_page.json()) == 1


def test_manager_can_cancel_any_reservation(session_factory: sessionmaker) -> None:
    from reservations.models import User

    client = TestClient(app)
    court_id = seed_court(session_factory)
    player_token = register_and_login(client, "olivia@example.com")
    created = client.post(
        "/reservations",
        json={"court_id": court_id, "start_time": at(18), "end_time": at(19)},
        headers={"Authorization": f"Bearer {player_token}"},
    ).json()

    manager_token = register_and_login(client, "peter-manager@example.com")
    with session_factory() as session:
        manager = session.query(User).filter_by(email="peter-manager@example.com").one()
        make_venue_manager(session, manager)
        session.commit()

    response = client.post(
        f"/reservations/{created['id']}/cancel",
        headers={"Authorization": f"Bearer {manager_token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_reservation_series_books_multiple_weeks(session_factory: sessionmaker) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "zara@example.com")

    response = client.post(
        "/reservations/series",
        json={
            "court_id": court_id,
            "start_time": at(18),
            "end_time": at(19),
            "weeks": 2,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["booked"]) == 2
    assert body["failed_weeks"] == []
    assert all(r["series_id"] == body["series_id"] for r in body["booked"])


def test_reservation_series_respects_active_reservation_limit(
    session_factory: sessionmaker,
) -> None:
    """A player is capped at 3 active reservations — a series longer than
    that must stop booking once the cap is hit instead of bypassing it."""
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "yusuf@example.com")

    response = client.post(
        "/reservations/series",
        json={
            "court_id": court_id,
            "start_time": at(18),
            "end_time": at(19),
            "weeks": 5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["booked"]) == 3
    assert body["failed_weeks"] == [4, 5]


def test_reservation_series_rejected_when_already_at_active_limit(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    court_id = seed_court(session_factory)
    token = register_and_login(client, "xena@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    for hour in (9, 11, 13):
        response = client.post(
            "/reservations",
            json={
                "court_id": court_id,
                "start_time": at(hour),
                "end_time": at(hour + 1),
            },
            headers=headers,
        )
        assert response.status_code == 201

    response = client.post(
        "/reservations/series",
        json={
            "court_id": court_id,
            "start_time": at(18),
            "end_time": at(19),
            "weeks": 2,
        },
        headers=headers,
    )
    assert response.status_code == 409
