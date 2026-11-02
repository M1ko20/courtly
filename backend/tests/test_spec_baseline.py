"""Executable form of docs/specification-v0.1.md.

Every test name starts with the id of the verification example (VE-xx.y) it
executes, so the specification, this file and the evidence in
docs/evidence-and-evolution.md can be followed in both directions.

These run against a real PostgreSQL on purpose: BR-02 is enforced by an
exclusion constraint, and REQ-02/REQ-07 are about concurrent transactions.
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from support import default_venue_id, make_venue_manager

from reservations import worker
from reservations.main import app
from reservations.models import (
    Court,
    FacilityBlock,
    Notification,
    NotificationType,
    Reservation,
    ReservationEvent,
    ReservationEventType,
    ReservationStatus,
    SportType,
    User,
    UserRole,
)
from reservations.security import create_access_token, hash_password

PRAGUE = ZoneInfo("Europe/Prague")
DAYS_AHEAD = 3  # inside BR-05's window whenever the suite runs


def at(hour: int, minute: int = 0, days: int = DAYS_AHEAD) -> datetime:
    day = (datetime.now(PRAGUE) + timedelta(days=days)).date()
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=PRAGUE)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_user(
    session_factory: sessionmaker, email: str, role: UserRole = UserRole.PLAYER
) -> tuple[uuid.UUID, str]:
    with session_factory() as session:
        user = User(
            name="Spec User",
            email=email,
            password_hash=hash_password("supersecret"),
            role=role,
        )
        session.add(user)
        if role == UserRole.VENUE_MANAGER:
            make_venue_manager(session, user)
        session.commit()
        return user.id, create_access_token(str(user.id))


def make_court(
    session_factory: sessionmaker,
    name: str = "Spec Court",
    active: bool = True,
    requires_approval: bool = False,
) -> uuid.UUID:
    with session_factory() as session:
        court = Court(venue_id=default_venue_id(session), 
            name=name,
            sport_type=SportType.TENNIS,
            indoor=False,
            active=active,
            requires_approval=requires_approval,
        )
        session.add(court)
        session.commit()
        return court.id


def add_reservation(
    session_factory: sessionmaker,
    court_id: uuid.UUID,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
    status: ReservationStatus,
    hold_expires_at: datetime | None = None,
    approval_expires_at: datetime | None = None,
) -> uuid.UUID:
    """Insert a reservation directly — the only way to reach states/times the API refuses to create."""
    with session_factory() as session:
        reservation = Reservation(
            court_id=court_id,
            user_id=user_id,
            start_time=start,
            end_time=end,
            status=status,
            hold_expires_at=hold_expires_at,
            approval_expires_at=approval_expires_at,
        )
        session.add(reservation)
        session.commit()
        return reservation.id


def create(client: TestClient, token: str | None, court_id: uuid.UUID, start, end):
    payload = {
        "court_id": str(court_id),
        "start_time": start if isinstance(start, str) else start.isoformat(),
        "end_time": end if isinstance(end, str) else end.isoformat(),
    }
    return client.post(
        "/reservations", json=payload, headers=bearer(token) if token else {}
    )


def check(client: TestClient, court_id: uuid.UUID, start: datetime, end: datetime):
    return client.get(
        f"/courts/{court_id}/availability/check",
        params={"start_time": start.isoformat(), "end_time": end.isoformat()},
    )


def status_of(
    session_factory: sessionmaker, reservation_id: uuid.UUID
) -> ReservationStatus:
    with session_factory() as session:
        return session.get(Reservation, reservation_id).status


def reservation_count(session_factory: sessionmaker, court_id: uuid.UUID) -> int:
    with session_factory() as session:
        return session.scalar(
            select(func.count())
            .select_from(Reservation)
            .where(Reservation.court_id == court_id)
        )


def event_types(
    session_factory: sessionmaker, reservation_id: uuid.UUID
) -> list[ReservationEventType]:
    with session_factory() as session:
        rows = session.scalars(
            select(ReservationEvent)
            .where(ReservationEvent.reservation_id == reservation_id)
            .order_by(ReservationEvent.created_at)
        )
        return [row.event_type for row in rows]


def hold_in_future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=5)


# --------------------------------------------------------------------------- OP-01 Create Reservation


def test_ve_01_1_valid_create_holds_the_slot(session_factory: sessionmaker) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)

    before = datetime.now(timezone.utc)
    response = create(client, token, court_id, at(18), at(19))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    hold = datetime.fromisoformat(body["hold_expires_at"])
    assert (
        before + timedelta(minutes=4, seconds=50)
        < hold
        < datetime.now(timezone.utc) + timedelta(minutes=5, seconds=10)
    )
    assert reservation_count(session_factory, court_id) == 1
    assert event_types(session_factory, uuid.UUID(body["id"])) == [
        ReservationEventType.CREATED
    ]
    with session_factory() as session:
        kinds = [
            n.type
            for n in session.scalars(
                select(Notification).where(Notification.user_id == user_id)
            )
        ]
    assert kinds == [NotificationType.RESERVATION_CREATED]
    # the hold blocks the court for everybody (BR-02, cross-check with OP-02)
    assert check(client, court_id, at(18), at(19)).json()["available"] is False


def test_ve_01_2_start_equal_to_end_is_invalid_input(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    _, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)

    response = create(client, token, court_id, at(18), at(18))

    assert response.status_code == 422
    assert reservation_count(session_factory, court_id) == 0


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2030-01-01T18:00:00", "2030-01-01T19:00:00+01:00"),  # naive start
        ("2030-01-01T18:00:00+01:00", "2030-01-01T19:00:00"),  # naive end
    ],
)
def test_ve_01_2b_naive_times_are_invalid_input_not_a_server_error(
    session_factory: sessionmaker, start: str, end: str
) -> None:
    client = TestClient(app, raise_server_exceptions=False)
    _, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)

    response = create(client, token, court_id, start, end)

    assert response.status_code == 422
    assert reservation_count(session_factory, court_id) == 0


@pytest.mark.parametrize("active", [None, False])
def test_ve_01_3_unknown_or_inactive_court_is_not_found(
    session_factory: sessionmaker, active: bool | None
) -> None:
    client = TestClient(app)
    _, token = make_user(session_factory, "u@example.com")
    court_id = (
        uuid.uuid4() if active is None else make_court(session_factory, active=False)
    )

    response = create(client, token, court_id, at(18), at(19))

    assert response.status_code == 404
    assert reservation_count(session_factory, court_id) == 0


def test_ve_01_4_missing_token_is_unauthenticated(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    court_id = make_court(session_factory)

    response = create(client, None, court_id, at(18), at(19))

    assert response.status_code == 401
    assert reservation_count(session_factory, court_id) == 0


@pytest.mark.parametrize(
    ("start", "duration_minutes", "created"),
    [
        (at(21, 0), 60, True),  # ends exactly at closing time 22:00
        (at(7, 0), 60, True),  # starts exactly at opening time 07:00
        (at(21, 30), 60, False),  # would end 22:30
        (at(6, 30), 60, False),  # would start before opening
        (at(18, 0), 45, False),  # duration not 60/90/120
        (at(18, 15), 60, False),  # not on :00/:30
    ],
)
def test_ve_01_5_slot_shape_and_opening_hours_boundaries(
    session_factory: sessionmaker, start: datetime, duration_minutes: int, created: bool
) -> None:
    client = TestClient(app)
    _, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)

    response = create(
        client, token, court_id, start, start + timedelta(minutes=duration_minutes)
    )

    assert response.status_code == (201 if created else 422)
    assert reservation_count(session_factory, court_id) == (1 if created else 0)


def test_ve_01_6_booking_window_boundaries_with_an_injected_clock() -> None:
    from reservations.booking_validation import check_within_booking_window

    now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)

    def rejected(start: datetime) -> bool:
        try:
            check_within_booking_window(start, now=now)
        except HTTPException as exc:
            assert exc.status_code == 409
            return True
        return False

    assert rejected(now + timedelta(minutes=14, seconds=59))  # too soon
    assert not rejected(now + timedelta(minutes=15))  # earliest accepted instant
    assert not rejected(now + timedelta(days=14))  # latest accepted instant
    assert rejected(now + timedelta(days=14, seconds=1))  # too far ahead


def test_ve_01_7_overlap_conflicts_but_touching_intervals_do_not(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    _, first = make_user(session_factory, "first@example.com")
    _, second = make_user(session_factory, "second@example.com")
    court_id = make_court(session_factory)
    assert create(client, first, court_id, at(18), at(19)).status_code == 201

    overlapping = create(client, second, court_id, at(18, 30), at(19, 30))
    touching_after = create(client, second, court_id, at(19), at(20))
    touching_before = create(client, second, court_id, at(17), at(18))

    assert overlapping.status_code == 409
    assert touching_after.status_code == 201
    assert touching_before.status_code == 201


def test_ve_01_8_fourth_active_reservation_is_rejected(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    _, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)
    for hour in (8, 10, 12):
        assert (
            create(client, token, court_id, at(hour), at(hour + 1)).status_code == 201
        )

    response = create(client, token, court_id, at(14), at(15))

    assert response.status_code == 409
    assert reservation_count(session_factory, court_id) == 3


def test_ve_01_9_concurrent_creates_of_the_same_slot_yield_exactly_one_winner(
    session_factory: sessionmaker,
) -> None:
    attempts = 8
    court_id = make_court(session_factory)
    tokens = [
        make_user(session_factory, f"racer{i}@example.com")[1] for i in range(attempts)
    ]
    barrier = threading.Barrier(attempts)
    codes: list[int] = []
    lock = threading.Lock()

    def attempt(token: str) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        barrier.wait()
        code = create(client, token, court_id, at(18), at(19)).status_code
        with lock:
            codes.append(code)

    threads = [threading.Thread(target=attempt, args=(token,)) for token in tokens]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(codes) == [201] + [409] * (attempts - 1), codes
    assert reservation_count(session_factory, court_id) == 1


# --------------------------------------------------------------------------- OP-02 Check Availability


@pytest.mark.parametrize(
    ("start", "end", "available"),
    [
        (at(9), at(10), True),  # touches the start of the confirmed interval
        (at(10, 30), at(11, 30), False),  # overlaps
        (at(11), at(12), True),  # touches the end
        (at(10), at(11), False),  # identical interval
    ],
)
def test_ve_02_1_to_3_confirmed_reservation_half_open_semantics(
    session_factory: sessionmaker, start: datetime, end: datetime, available: bool
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)
    add_reservation(
        session_factory, court_id, user_id, at(10), at(11), ReservationStatus.CONFIRMED
    )

    response = check(client, court_id, start, end)

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is available
    assert body["reason"] == (None if available else "RESERVATION_OVERLAP")


@pytest.mark.parametrize(
    "released_as",
    [ReservationStatus.CANCELLED, ReservationStatus.EXPIRED, ReservationStatus.NO_SHOW],
)
def test_ve_02_4_pending_blocks_until_it_is_released(
    session_factory: sessionmaker, released_as: ReservationStatus
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(10),
        at(11),
        ReservationStatus.PENDING,
        hold_in_future(),
    )
    assert check(client, court_id, at(10), at(11)).json()["available"] is False

    with session_factory() as session:
        session.get(Reservation, reservation_id).status = released_as
        session.commit()

    assert check(client, court_id, at(10), at(11)).json()["available"] is True


def test_ve_02_5_facility_block_makes_the_interval_unavailable(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    manager_id, _ = make_user(session_factory, "m@example.com", UserRole.VENUE_MANAGER)
    court_id = make_court(session_factory)
    with session_factory() as session:
        session.add(
            FacilityBlock(
                court_id=court_id,
                start_time=at(10),
                end_time=at(12),
                reason="Resurfacing",
                created_by_id=manager_id,
            )
        )
        session.commit()

    inside = check(client, court_id, at(11), at(12))
    after = check(client, court_id, at(12), at(13))

    assert inside.json() == {
        "court_id": str(court_id),
        "start_time": at(11).isoformat(),
        "end_time": at(12).isoformat(),
        "available": False,
        "reason": "FACILITY_BLOCK",
    }
    assert after.json()["available"] is True


def test_ve_02_6_invalid_requests_are_rejected_and_change_nothing(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)
    inactive_id = make_court(session_factory, "Closed Court", active=False)
    reservation_id = add_reservation(
        session_factory, court_id, user_id, at(10), at(11), ReservationStatus.CONFIRMED
    )

    assert check(client, uuid.uuid4(), at(10), at(11)).status_code == 404
    assert check(client, inactive_id, at(10), at(11)).status_code == 404
    assert check(client, court_id, at(10), at(10)).status_code == 422
    assert check(client, court_id, at(10, 15), at(11, 15)).status_code == 422

    assert reservation_count(session_factory, court_id) == 1
    assert status_of(session_factory, reservation_id) == ReservationStatus.CONFIRMED
    assert event_types(session_factory, reservation_id) == []


# --------------------------------------------------------------------------- OP-03 Confirm Reservation


def confirm(client: TestClient, token: str | None, reservation_id: uuid.UUID):
    return client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=bearer(token) if token else {},
    )


def cancel(client: TestClient, token: str | None, reservation_id: uuid.UUID):
    return client.post(
        f"/reservations/{reservation_id}/cancel", headers=bearer(token) if token else {}
    )


def test_ve_03_1_confirm_keeps_the_slot_blocked_and_records_the_event(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(18),
        at(19),
        ReservationStatus.PENDING,
        hold_in_future(),
    )

    response = confirm(client, token, reservation_id)

    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"
    assert response.json()["hold_expires_at"] is None
    assert check(client, court_id, at(18), at(19)).json()["available"] is False
    assert event_types(session_factory, reservation_id) == [
        ReservationEventType.CONFIRMED
    ]
    with session_factory() as session:
        kinds = [
            n.type
            for n in session.scalars(
                select(Notification).where(Notification.user_id == user_id)
            )
        ]
    assert kinds == [NotificationType.RESERVATION_CONFIRMED]


@pytest.mark.parametrize(
    "state",
    [
        ReservationStatus.CONFIRMED,
        ReservationStatus.CANCELLED,
        ReservationStatus.EXPIRED,
    ],
)
# Both court kinds: Confirm/Reject take a different path per court
# kind, so a precondition must hold on each (C06 F1 sweep, risk R-05).
@pytest.mark.parametrize("requires_approval", [False, True])
def test_ve_03_2_confirm_from_any_other_state_is_a_conflict(
    session_factory: sessionmaker, state: ReservationStatus, requires_approval: bool
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory, requires_approval=requires_approval)
    reservation_id = add_reservation(
        session_factory, court_id, user_id, at(18), at(19), state
    )

    response = confirm(client, token, reservation_id)

    assert response.status_code == 409
    assert status_of(session_factory, reservation_id) == state


# Both court kinds: Confirm/Reject take a different path per court
# kind, so a precondition must hold on each (C06 F1 sweep, risk R-05).
@pytest.mark.parametrize("requires_approval", [False, True])
def test_ve_03_3_expired_hold_cannot_be_confirmed_and_is_then_swept(
    session_factory: sessionmaker, requires_approval: bool
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory, requires_approval=requires_approval)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(18),
        at(19),
        ReservationStatus.PENDING,
        datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    response = confirm(client, token, reservation_id)

    assert response.status_code == 409
    assert status_of(session_factory, reservation_id) == ReservationStatus.PENDING
    assert (
        check(client, court_id, at(18), at(19)).json()["available"] is False
    )  # still held until swept

    worker.tick(session_factory)

    assert status_of(session_factory, reservation_id) == ReservationStatus.EXPIRED
    assert check(client, court_id, at(18), at(19)).json()["available"] is True


# Both court kinds: Confirm/Reject take a different path per court
# kind, so a precondition must hold on each (C06 F1 sweep, risk R-05).
@pytest.mark.parametrize("requires_approval", [False, True])
def test_ve_03_4_confirm_on_a_deactivated_court_is_a_conflict(
    session_factory: sessionmaker, requires_approval: bool
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory, requires_approval=requires_approval)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(18),
        at(19),
        ReservationStatus.PENDING,
        hold_in_future(),
    )
    with session_factory() as session:
        session.get(Court, court_id).active = False
        session.commit()

    response = confirm(client, token, reservation_id)

    assert response.status_code == 409
    assert status_of(session_factory, reservation_id) == ReservationStatus.PENDING


def test_ve_03_5_only_owner_or_manager_may_confirm(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    owner_id, _ = make_user(session_factory, "owner@example.com")
    _, stranger = make_user(session_factory, "stranger@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        owner_id,
        at(18),
        at(19),
        ReservationStatus.PENDING,
        hold_in_future(),
    )

    assert confirm(client, None, reservation_id).status_code == 401
    assert confirm(client, stranger, reservation_id).status_code == 403
    assert status_of(session_factory, reservation_id) == ReservationStatus.PENDING
    assert confirm(client, manager, reservation_id).status_code == 200
    assert status_of(session_factory, reservation_id) == ReservationStatus.CONFIRMED


def test_ve_03_6_confirm_racing_cancel_always_ends_cancelled(
    session_factory: sessionmaker,
) -> None:
    user_id, token = make_user(session_factory, "u@example.com")

    for round_number in range(20):
        court_id = make_court(session_factory, f"Race Court {round_number}")
        reservation_id = add_reservation(
            session_factory,
            court_id,
            user_id,
            at(18),
            at(19),
            ReservationStatus.PENDING,
            hold_in_future(),
        )
        barrier = threading.Barrier(2)
        codes: dict[str, int] = {}

        def call(name: str, action) -> None:
            client = TestClient(app, raise_server_exceptions=False)
            barrier.wait()
            codes[name] = action(client, token, reservation_id).status_code

        threads = [
            threading.Thread(target=call, args=("confirm", confirm)),
            threading.Thread(target=call, args=("cancel", cancel)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert codes["cancel"] == 200, (round_number, codes)
        assert codes["confirm"] in (200, 409), (round_number, codes)
        assert (
            status_of(session_factory, reservation_id) == ReservationStatus.CANCELLED
        ), (round_number, codes)
        assert (
            event_types(session_factory, reservation_id).count(
                ReservationEventType.CANCELLED
            )
            == 1
        )


def test_ve_03_7_sweep_expires_only_expired_holds(
    session_factory: sessionmaker,
) -> None:
    user_id, _ = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)
    stale = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(10),
        at(11),
        ReservationStatus.PENDING,
        datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    fresh = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(12),
        at(13),
        ReservationStatus.PENDING,
        hold_in_future(),
    )

    worker.tick(session_factory)

    assert status_of(session_factory, stale) == ReservationStatus.EXPIRED
    assert status_of(session_factory, fresh) == ReservationStatus.PENDING
    assert event_types(session_factory, stale) == [ReservationEventType.EXPIRED]
    with session_factory() as session:
        kinds = [
            n.type
            for n in session.scalars(
                select(Notification).where(Notification.user_id == user_id)
            )
        ]
    assert kinds == [NotificationType.RESERVATION_EXPIRED]


# --------------------------------------------------------------------------- OP-04 Cancel Reservation


@pytest.mark.parametrize(
    "state", [ReservationStatus.PENDING, ReservationStatus.CONFIRMED]
)
def test_ve_04_1_and_2_cancel_before_start_frees_the_slot(
    session_factory: sessionmaker, state: ReservationStatus
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(18),
        at(19),
        state,
        hold_in_future() if state == ReservationStatus.PENDING else None,
    )
    assert check(client, court_id, at(18), at(19)).json()["available"] is False

    response = cancel(client, token, reservation_id)

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert check(client, court_id, at(18), at(19)).json()["available"] is True
    assert reservation_count(session_factory, court_id) == 1  # retained, not deleted
    assert event_types(session_factory, reservation_id) == [
        ReservationEventType.CANCELLED
    ]


def test_ve_04_3_started_or_fulfilling_reservations_cannot_be_cancelled(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "u@example.com")
    now = datetime.now(timezone.utc)
    started_court = make_court(session_factory, "Started")
    started = add_reservation(
        session_factory,
        started_court,
        user_id,
        now - timedelta(seconds=1),
        now + timedelta(hours=1),
        ReservationStatus.CONFIRMED,
    )
    checked_in_court = make_court(session_factory, "Checked in")
    checked_in = add_reservation(
        session_factory,
        checked_in_court,
        user_id,
        at(18),
        at(19),
        ReservationStatus.CHECKED_IN,
    )

    assert cancel(client, token, started).status_code == 409
    assert cancel(client, token, checked_in).status_code == 409
    assert status_of(session_factory, started) == ReservationStatus.CONFIRMED
    assert status_of(session_factory, checked_in) == ReservationStatus.CHECKED_IN


def test_ve_04_4_cancellation_boundary_is_strictly_before_start() -> None:
    from reservations.lifecycle import check_cancellable

    start = datetime(2030, 1, 1, 18, 0, tzinfo=timezone.utc)
    reservation = Reservation(
        start_time=start,
        end_time=start + timedelta(hours=1),
        status=ReservationStatus.CONFIRMED,
    )

    check_cancellable(
        reservation, now=start - timedelta(microseconds=1)
    )  # allowed: does not raise
    with pytest.raises(HTTPException) as exc_info:
        check_cancellable(reservation, now=start)
    assert exc_info.value.status_code == 409


@pytest.mark.parametrize(
    "state", [ReservationStatus.CANCELLED, ReservationStatus.EXPIRED]
)
def test_ve_04_5_cancelling_a_released_reservation_is_an_explicit_rejection(
    session_factory: sessionmaker, state: ReservationStatus
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory)
    reservation_id = add_reservation(
        session_factory, court_id, user_id, at(18), at(19), state
    )

    response = cancel(client, token, reservation_id)

    assert response.status_code == 409
    assert status_of(session_factory, reservation_id) == state


def test_ve_04_6_only_owner_or_manager_may_cancel(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    owner_id, _ = make_user(session_factory, "owner@example.com")
    _, stranger = make_user(session_factory, "stranger@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory)
    reservation_id = add_reservation(
        session_factory, court_id, owner_id, at(18), at(19), ReservationStatus.CONFIRMED
    )

    assert cancel(client, None, reservation_id).status_code == 401
    assert cancel(client, stranger, reservation_id).status_code == 403
    assert status_of(session_factory, reservation_id) == ReservationStatus.CONFIRMED
    assert cancel(client, manager, reservation_id).status_code == 200
    assert status_of(session_factory, reservation_id) == ReservationStatus.CANCELLED


def test_ve_04_7_a_cancelled_slot_can_be_booked_again(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    _, first = make_user(session_factory, "first@example.com")
    _, second = make_user(session_factory, "second@example.com")
    court_id = make_court(session_factory)
    created = create(client, first, court_id, at(18), at(19)).json()
    assert create(client, second, court_id, at(18), at(19)).status_code == 409

    assert cancel(client, first, uuid.UUID(created["id"])).status_code == 200

    assert create(client, second, court_id, at(18), at(19)).status_code == 201
