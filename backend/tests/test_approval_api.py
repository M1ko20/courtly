"""Executable form of the v0.2 additions in docs/specification.md: the
approval process (OP-05 Approve, OP-06 Reject, approval expiry, BR-11 "no
bypass"). Test names start with the id of the verification example they run.

The v0.1 examples (VE-01…VE-04) stay in test_spec_baseline.py and must still
pass unchanged under v0.2 — the change must not disturb courts that do not
require approval.
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker
from support import make_venue, make_venue_manager
from test_spec_baseline import (
    add_reservation,
    at,
    bearer,
    cancel,
    check,
    confirm,
    create,
    event_types,
    hold_in_future,
    make_court,
    make_user,
    status_of,
)

from reservations import approval_service, worker
from reservations.lifecycle import transition
from reservations.main import app
from reservations.models import (
    ACTIVE_RESERVATION_STATUSES,
    Court,
    Notification,
    NotificationType,
    Reservation,
    ReservationEventType,
    ReservationStatus,
    User,
    UserRole,
    WaitlistEntry,
    WaitlistStatus,
)

PENDING_APPROVAL = ReservationStatus.PENDING_APPROVAL


def approve(client: TestClient, token: str | None, reservation_id: uuid.UUID):
    return client.post(
        f"/reservations/{reservation_id}/approve",
        headers=bearer(token) if token else {},
    )


def reject(client: TestClient, token: str | None, reservation_id: uuid.UUID):
    return client.post(
        f"/reservations/{reservation_id}/reject", headers=bearer(token) if token else {}
    )


def in_hours(hours: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def request_pending(
    session_factory: sessionmaker,
    court_id: uuid.UUID,
    user_id: uuid.UUID,
    start: datetime | None = None,
    end: datetime | None = None,
    deadline: datetime | None = None,
) -> uuid.UUID:
    """A reservation already sitting in PENDING_APPROVAL with an open deadline."""
    return add_reservation(
        session_factory,
        court_id,
        user_id,
        start or at(18),
        end or at(19),
        PENDING_APPROVAL,
        approval_expires_at=deadline or in_hours(20),
    )


def notification_types(
    session_factory: sessionmaker, user_id: uuid.UUID
) -> list[NotificationType]:
    with session_factory() as session:
        rows = session.scalars(
            select(Notification).where(Notification.user_id == user_id)
        )
        return [row.type for row in rows]


# ------------------------------------------------------- OP-01 / OP-02 / OP-03 / OP-04 under v0.2


def test_ve_01_10_pending_approval_counts_toward_the_active_limit(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "u@example.com")
    normal = make_court(session_factory, "Normal")
    gated = make_court(session_factory, "Gated", requires_approval=True)
    add_reservation(
        session_factory, normal, user_id, at(8), at(9), ReservationStatus.CONFIRMED
    )
    add_reservation(
        session_factory, normal, user_id, at(10), at(11), ReservationStatus.CONFIRMED
    )
    request_pending(session_factory, gated, user_id)

    response = create(client, token, normal, at(14), at(15))

    assert response.status_code == 409


@pytest.mark.parametrize(
    "released_as",
    [
        ReservationStatus.REJECTED,
        ReservationStatus.EXPIRED,
        ReservationStatus.CANCELLED,
    ],
)
def test_ve_02_7_pending_approval_blocks_until_it_is_released(
    session_factory: sessionmaker, released_as: ReservationStatus
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)
    assert check(client, court_id, at(18), at(19)).json()["available"] is False

    with session_factory() as session:
        session.get(Reservation, reservation_id).status = released_as
        session.commit()

    assert check(client, court_id, at(18), at(19)).json()["available"] is True


def test_ve_03_8_confirm_on_an_approval_court_submits_a_request(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
    manager_a, _ = make_user(
        session_factory, "manager-a@example.com", UserRole.VENUE_MANAGER
    )
    manager_b, _ = make_user(
        session_factory, "manager-b@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
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
    body = response.json()
    assert body["status"] == "PENDING_APPROVAL"  # not CONFIRMED
    assert body["hold_expires_at"] is None
    deadline = datetime.fromisoformat(body["approval_expires_at"])
    assert in_hours(23.9) < deadline < in_hours(24.1)
    assert check(client, court_id, at(18), at(19)).json()["available"] is False
    assert event_types(session_factory, reservation_id) == [
        ReservationEventType.SUBMITTED
    ]
    assert notification_types(session_factory, user_id) == [
        NotificationType.RESERVATION_CHANGED
    ]
    assert notification_types(session_factory, manager_a) == [
        NotificationType.APPROVAL_REQUESTED
    ]
    assert notification_types(session_factory, manager_b) == [
        NotificationType.APPROVAL_REQUESTED
    ]


def test_ve_03_8b_a_normal_court_still_confirms_immediately(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
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

    assert confirm(client, token, reservation_id).json()["status"] == "CONFIRMED"


def test_ve_03_9_manager_confirm_on_behalf_is_still_only_a_submission(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(18),
        at(19),
        ReservationStatus.PENDING,
        hold_in_future(),
    )

    response = confirm(client, manager, reservation_id)

    assert response.status_code == 200
    assert response.json()["status"] == "PENDING_APPROVAL"


@pytest.mark.parametrize("state", [PENDING_APPROVAL, ReservationStatus.REJECTED])
def test_ve_03_10_confirm_is_not_an_approval(
    session_factory: sessionmaker, state: ReservationStatus
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(18),
        at(19),
        state,
        approval_expires_at=in_hours(5),
    )

    response = confirm(client, token, reservation_id)

    assert response.status_code == 409
    assert status_of(session_factory, reservation_id) == state


def test_ve_04_8_owner_can_withdraw_a_request_before_start(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)

    response = cancel(client, token, reservation_id)

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["approval_expires_at"] is None
    assert check(client, court_id, at(18), at(19)).json()["available"] is True
    assert approve(client, manager, reservation_id).status_code == 409


# --------------------------------------------------------------------------- OP-05 Approve


def test_ve_05_1_manager_approval_confirms_and_keeps_the_slot_blocked(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    manager_id, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)

    response = approve(client, manager, reservation_id)

    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"
    assert response.json()["approval_expires_at"] is None
    assert check(client, court_id, at(18), at(19)).json()["available"] is False
    history = client.get(
        f"/reservations/{reservation_id}/history", headers=bearer(manager)
    ).json()
    assert [(event["event_type"], event["actor_id"]) for event in history] == [
        ("CONFIRMED", str(manager_id))
    ]
    assert notification_types(session_factory, user_id) == [
        NotificationType.RESERVATION_CONFIRMED
    ]


def test_ve_05_2_the_owner_cannot_approve_their_own_request(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)

    assert approve(client, None, reservation_id).status_code == 401
    assert approve(client, token, reservation_id).status_code == 403
    assert reject(client, token, reservation_id).status_code == 403
    assert status_of(session_factory, reservation_id) == PENDING_APPROVAL


@pytest.mark.parametrize(
    "state",
    [
        ReservationStatus.PENDING,
        ReservationStatus.CONFIRMED,
        ReservationStatus.REJECTED,
    ],
)
# Both court kinds: on a normal court the PENDING -> CONFIRMED guards would
# pass, so only the OP-05 precondition (state = PENDING_APPROVAL) refuses it.
@pytest.mark.parametrize("requires_approval", [True, False])
def test_ve_05_3_approve_from_any_other_state_is_a_conflict(
    session_factory: sessionmaker, state: ReservationStatus, requires_approval: bool
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=requires_approval)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(18),
        at(19),
        state,
        hold_expires_at=hold_in_future()
        if state == ReservationStatus.PENDING
        else None,
    )

    assert approve(client, manager, reservation_id).status_code == 409
    assert status_of(session_factory, reservation_id) == state


def test_ve_05_4_a_request_past_its_deadline_cannot_be_approved(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(
        session_factory,
        court_id,
        user_id,
        deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    assert approve(client, manager, reservation_id).status_code == 409
    assert (
        status_of(session_factory, reservation_id) == PENDING_APPROVAL
    )  # until the sweep runs


def test_ve_05_4b_approval_on_a_deactivated_court_is_a_conflict(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)
    with session_factory() as session:
        session.get(Court, court_id).active = False
        session.commit()

    assert approve(client, manager, reservation_id).status_code == 409
    assert status_of(session_factory, reservation_id) == PENDING_APPROVAL


def test_ve_05_5_a_manager_may_approve_their_own_request(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    manager_id, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, manager_id)

    assert approve(client, manager, reservation_id).status_code == 200
    assert status_of(session_factory, reservation_id) == ReservationStatus.CONFIRMED


def test_ve_05_6_approve_racing_reject_has_exactly_one_winner(
    session_factory: sessionmaker,
) -> None:
    user_id, _ = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )

    for round_number in range(20):
        court_id = make_court(
            session_factory, f"Gated {round_number}", requires_approval=True
        )
        reservation_id = request_pending(session_factory, court_id, user_id)
        barrier = threading.Barrier(2)
        codes: dict[str, int] = {}

        def call(name: str, action) -> None:
            client = TestClient(app, raise_server_exceptions=False)
            barrier.wait()
            codes[name] = action(client, manager, reservation_id).status_code

        threads = [
            threading.Thread(target=call, args=("approve", approve)),
            threading.Thread(target=call, args=("reject", reject)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(codes.values()) == [200, 409], (round_number, codes)
        winner = (
            ReservationStatus.CONFIRMED
            if codes["approve"] == 200
            else ReservationStatus.REJECTED
        )
        assert status_of(session_factory, reservation_id) == winner, (
            round_number,
            codes,
        )


def test_ve_05_7_reschedule_cannot_move_an_approved_booking(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
    gated = make_court(session_factory, "Gated", requires_approval=True)
    normal = make_court(session_factory, "Normal")
    approved = add_reservation(
        session_factory, gated, user_id, at(18), at(19), ReservationStatus.CONFIRMED
    )
    plain = add_reservation(
        session_factory, normal, user_id, at(18), at(19), ReservationStatus.CONFIRMED
    )
    hold = add_reservation(
        session_factory,
        gated,
        user_id,
        at(10),
        at(11),
        ReservationStatus.PENDING,
        hold_in_future(),
    )
    move = {"start_time": at(20).isoformat(), "end_time": at(21).isoformat()}

    assert (
        client.patch(
            f"/reservations/{approved}/reschedule", json=move, headers=bearer(token)
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/reservations/{plain}/reschedule", json=move, headers=bearer(token)
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/reservations/{hold}/reschedule", json=move, headers=bearer(token)
        ).status_code
        == 200
    )


def test_ve_05_7b_reschedule_waits_for_a_concurrent_decision_and_sees_its_result(
    session_factory: sessionmaker,
) -> None:
    """A reschedule read the status before a concurrent Confirm/Approve could
    change it would write new times onto a request that was submitted for
    the *old* slot. It must wait for the row lock and re-check."""
    client = TestClient(app, raise_server_exceptions=False)
    user_id, token = make_user(session_factory, "player@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    hold = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(10),
        at(11),
        ReservationStatus.PENDING,
        hold_in_future(),
    )
    move = {"start_time": at(20).isoformat(), "end_time": at(21).isoformat()}
    result: dict[str, int] = {}

    with session_factory() as holder:  # plays a concurrent Confirm that is mid-flight
        holder.execute(
            select(Reservation).where(Reservation.id == hold).with_for_update()
        )
        thread = threading.Thread(
            target=lambda: result.update(
                code=client.patch(
                    f"/reservations/{hold}/reschedule", json=move, headers=bearer(token)
                ).status_code
            )
        )
        thread.start()
        thread.join(timeout=1.0)
        assert thread.is_alive(), "reschedule did not wait for the row lock"
        holder.get(
            Reservation, hold
        ).status = PENDING_APPROVAL  # the concurrent submission commits
        holder.commit()
    thread.join(timeout=10)

    assert result["code"] == 409  # it saw PENDING_APPROVAL, which cannot be rescheduled
    with session_factory() as session:
        assert session.get(Reservation, hold).start_time == at(10)


def test_ve_05_8_approve_racing_cancel_always_ends_cancelled(
    session_factory: sessionmaker,
) -> None:
    user_id, token = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )

    for round_number in range(20):
        court_id = make_court(
            session_factory, f"Gated {round_number}", requires_approval=True
        )
        reservation_id = request_pending(session_factory, court_id, user_id)
        barrier = threading.Barrier(2)
        codes: dict[str, int] = {}

        def call(name: str, action, who: str) -> None:
            client = TestClient(app, raise_server_exceptions=False)
            barrier.wait()
            codes[name] = action(client, who, reservation_id).status_code

        threads = [
            threading.Thread(target=call, args=("approve", approve, manager)),
            threading.Thread(target=call, args=("cancel", cancel, token)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert codes["cancel"] == 200, (round_number, codes)
        assert codes["approve"] in (200, 409), (round_number, codes)
        assert (
            status_of(session_factory, reservation_id) == ReservationStatus.CANCELLED
        ), (round_number, codes)


# --------------------------------------------------------------------------- OP-06 Reject


def test_ve_06_1_reject_releases_the_slot_and_offers_it_to_the_waitlist(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    waiting_id, _ = make_user(session_factory, "waiting@example.com")
    manager_id, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)
    with session_factory() as session:
        entry = WaitlistEntry(
            court_id=court_id, user_id=waiting_id, start_time=at(18), end_time=at(19)
        )
        session.add(entry)
        session.commit()
        entry_id = entry.id

    response = reject(client, manager, reservation_id)

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert check(client, court_id, at(18), at(19)).json()["available"] is True
    history = client.get(
        f"/reservations/{reservation_id}/history", headers=bearer(manager)
    ).json()
    assert [(event["event_type"], event["actor_id"]) for event in history] == [
        ("REJECTED", str(manager_id))
    ]
    assert notification_types(session_factory, user_id) == [
        NotificationType.RESERVATION_REJECTED
    ]
    with session_factory() as session:
        assert session.get(WaitlistEntry, entry_id).status == WaitlistStatus.OFFERED


def test_ve_06_2_a_player_owner_or_not_cannot_reject(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
    _, other_token = make_user(session_factory, "other@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)

    assert reject(client, None, reservation_id).status_code == 401
    assert reject(client, token, reservation_id).status_code == 403
    assert reject(client, other_token, reservation_id).status_code == 403
    assert status_of(session_factory, reservation_id) == PENDING_APPROVAL


@pytest.mark.parametrize(
    "state",
    [
        ReservationStatus.PENDING,
        ReservationStatus.CONFIRMED,
        ReservationStatus.REJECTED,
    ],
)
# Both court kinds: Confirm/Reject take a different path per court
# kind, so a precondition must hold on each (C06 F1 sweep, risk R-05).
@pytest.mark.parametrize("requires_approval", [True, False])
def test_ve_06_3_reject_from_any_other_state_is_a_conflict(
    session_factory: sessionmaker, state: ReservationStatus, requires_approval: bool
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=requires_approval)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(18),
        at(19),
        state,
        hold_expires_at=hold_in_future()
        if state == ReservationStatus.PENDING
        else None,
    )

    assert reject(client, manager, reservation_id).status_code == 409
    assert status_of(session_factory, reservation_id) == state


def test_ve_06_4_a_request_past_its_deadline_cannot_be_rejected(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(
        session_factory,
        court_id,
        user_id,
        deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    assert reject(client, manager, reservation_id).status_code == 409
    assert status_of(session_factory, reservation_id) == PENDING_APPROVAL


def test_ve_06_5_a_rejected_slot_can_be_requested_again(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)
    assert create(client, token, court_id, at(18), at(19)).status_code == 409

    assert reject(client, manager, reservation_id).status_code == 200

    assert create(client, token, court_id, at(18), at(19)).status_code == 201


# --------------------------------------------------------------------------- approval expiry


def test_ve_07_1_an_undecided_request_expires_and_releases_the_slot(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    waiting_id, _ = make_user(session_factory, "waiting@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(
        session_factory,
        court_id,
        user_id,
        deadline=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    with session_factory() as session:
        entry = WaitlistEntry(
            court_id=court_id, user_id=waiting_id, start_time=at(18), end_time=at(19)
        )
        session.add(entry)
        session.commit()
        entry_id = entry.id
    assert (
        check(client, court_id, at(18), at(19)).json()["available"] is False
    )  # still blocking until swept

    worker.tick(session_factory)

    assert status_of(session_factory, reservation_id) == ReservationStatus.EXPIRED
    assert check(client, court_id, at(18), at(19)).json()["available"] is True
    assert event_types(session_factory, reservation_id) == [
        ReservationEventType.EXPIRED
    ]
    assert notification_types(session_factory, user_id) == [
        NotificationType.RESERVATION_EXPIRED
    ]
    with session_factory() as session:
        assert session.get(WaitlistEntry, entry_id).status == WaitlistStatus.OFFERED
    assert approve(client, manager, reservation_id).status_code == 409
    assert reject(client, manager, reservation_id).status_code == 409


def test_ve_07_2_delay_a_pending_request_is_not_decided_by_the_passage_of_time(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(
        session_factory, court_id, user_id, deadline=in_hours(5)
    )

    worker.tick(session_factory)
    worker.tick(session_factory)

    assert status_of(session_factory, reservation_id) == PENDING_APPROVAL
    assert check(client, court_id, at(18), at(19)).json()["available"] is False


def test_ve_07_3_approval_deadline_is_the_earlier_of_24h_and_the_start() -> None:
    now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)

    far = now + timedelta(days=3)
    assert approval_service.approval_deadline(far, now=now) == now + timedelta(hours=24)

    near = now + timedelta(hours=5)
    assert (
        approval_service.approval_deadline(near, now=now) == near
    )  # never after the slot starts

    exactly_24h = now + timedelta(hours=24)
    assert approval_service.approval_deadline(exactly_24h, now=now) == exactly_24h


# --------------------------------------------------------------------------- no bypass (BR-11)


def test_ve_08_1_accepting_a_waitlist_offer_on_an_approval_court_is_a_request(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    waiting_id, waiting_token = make_user(session_factory, "waiting@example.com")
    manager_id, _ = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory, requires_approval=True)
    with session_factory() as session:
        entry = WaitlistEntry(
            court_id=court_id,
            user_id=waiting_id,
            start_time=at(18),
            end_time=at(19),
            status=WaitlistStatus.OFFERED,
            offer_expires_at=in_hours(0.2),
        )
        session.add(entry)
        session.commit()
        entry_id = entry.id

    response = client.post(
        f"/waitlist/{entry_id}/accept", headers=bearer(waiting_token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PENDING_APPROVAL"  # not CONFIRMED
    assert (
        in_hours(23.9)
        < datetime.fromisoformat(body["approval_expires_at"])
        < in_hours(24.1)
    )
    assert notification_types(session_factory, manager_id) == [
        NotificationType.APPROVAL_REQUESTED
    ]
    assert event_types(session_factory, uuid.UUID(body["id"])) == [
        ReservationEventType.CREATED,
        ReservationEventType.SUBMITTED,
    ]


def test_ve_08_2_the_state_machine_itself_refuses_the_bypass(
    session_factory: sessionmaker,
) -> None:
    user_id, _ = make_user(session_factory, "player@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    hold = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(18),
        at(19),
        ReservationStatus.PENDING,
        hold_in_future(),
    )
    request = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(10),
        at(11),
        PENDING_APPROVAL,
        approval_expires_at=in_hours(5),
    )

    with session_factory() as session:
        with pytest.raises(HTTPException) as hold_error:
            transition(
                session, session.get(Reservation, hold), ReservationStatus.CONFIRMED
            )
        with pytest.raises(HTTPException) as request_error:
            transition(
                session, session.get(Reservation, request), ReservationStatus.CONFIRMED
            )
        with pytest.raises(HTTPException) as reject_error:
            transition(
                session, session.get(Reservation, request), ReservationStatus.REJECTED
            )
    assert (
        hold_error.value.status_code,
        request_error.value.status_code,
        reject_error.value.status_code,
    ) == (
        409,
        409,
        409,
    )
    assert status_of(session_factory, hold) == ReservationStatus.PENDING
    assert status_of(session_factory, request) == PENDING_APPROVAL


def test_ve_08_3_switching_the_flag_on_is_grandfathered(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
    _, manager = make_user(
        session_factory, "manager@example.com", UserRole.VENUE_MANAGER
    )
    court_id = make_court(session_factory)
    booked = add_reservation(
        session_factory, court_id, user_id, at(18), at(19), ReservationStatus.CONFIRMED
    )
    hold = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(10),
        at(11),
        ReservationStatus.PENDING,
        hold_in_future(),
    )

    switch = client.patch(
        f"/courts/{court_id}", json={"requires_approval": True}, headers=bearer(manager)
    )
    assert switch.status_code == 200
    assert switch.json()["requires_approval"] is True

    assert (
        status_of(session_factory, booked) == ReservationStatus.CONFIRMED
    )  # untouched
    assert (
        confirm(client, token, hold).json()["status"] == "PENDING_APPROVAL"
    )  # decided at Confirm time


def test_ve_08_4_only_a_manager_can_switch_the_flag_and_everyone_can_read_it(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    _, player = make_user(session_factory, "player@example.com")
    court_id = make_court(session_factory, requires_approval=True)

    assert (
        client.patch(
            f"/courts/{court_id}",
            json={"requires_approval": False},
            headers=bearer(player),
        ).status_code
        == 403
    )
    assert client.get(f"/courts/{court_id}").json()["requires_approval"] is True


# --------------------------------------------------------------------------- guards against drift


def test_the_exclusion_constraint_blocks_exactly_the_active_statuses(
    session_factory: sessionmaker,
) -> None:
    """Known pitfall #4 made mechanical: the constraint's WHERE list and
    ACTIVE_RESERVATION_STATUSES are two separate definitions (driver AD-2);
    this fails the moment they disagree."""
    with session_factory() as session:
        definition = session.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'no_overlapping_active_reservations'"
            )
        )
    in_constraint = {
        status for status in ReservationStatus if f"'{status.value}'" in definition
    }
    assert in_constraint == set(ACTIVE_RESERVATION_STATUSES)
    # ...and both say what docs/specification.md BR-02 says, written down
    # here rather than read from the code.
    br_02_blocking_states = {
        ReservationStatus.PENDING,
        ReservationStatus.PENDING_APPROVAL,
        ReservationStatus.CONFIRMED,
        ReservationStatus.CHECKED_IN,
    }
    assert in_constraint == br_02_blocking_states


def test_a_pending_approval_reservation_is_tentative_in_the_calendar(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)

    response = client.get(f"/reservations/{reservation_id}/ics", headers=bearer(token))

    assert response.status_code == 200
    assert "STATUS:TENTATIVE" in response.text


# ------------------------------------------------------- v0.3: venue-scoped approvers (BR-10)


def _manager_of_another_venue(
    session_factory: sessionmaker, email: str
) -> tuple[uuid.UUID, str]:
    """A VENUE_MANAGER assigned only to a venue that isn't the test courts' venue."""
    user_id, token = make_user(session_factory, email)
    with session_factory() as session:
        user = session.get(User, user_id)
        make_venue_manager(session, user, make_venue(session, f"Elsewhere {email}"))
        session.commit()
    return user_id, token


def test_ve_05_9_a_manager_of_another_venue_cannot_approve(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    _, outsider = _manager_of_another_venue(session_factory, "outsider@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)

    response = approve(client, outsider, reservation_id)

    assert response.status_code == 403
    assert status_of(session_factory, reservation_id) == PENDING_APPROVAL


def test_ve_05_10_owning_the_request_does_not_make_another_venues_manager_an_approver(
    session_factory: sessionmaker,
) -> None:
    """A manager booking at a venue they don't manage is just a player there."""
    client = TestClient(app)
    outsider_id, outsider = _manager_of_another_venue(
        session_factory, "outsider@example.com"
    )
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, outsider_id)

    response = approve(client, outsider, reservation_id)

    assert response.status_code == 403
    assert status_of(session_factory, reservation_id) == PENDING_APPROVAL


def test_ve_06_6_a_manager_of_another_venue_cannot_reject(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, _ = make_user(session_factory, "player@example.com")
    _, outsider = _manager_of_another_venue(session_factory, "outsider@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = request_pending(session_factory, court_id, user_id)

    response = reject(client, outsider, reservation_id)

    assert response.status_code == 403
    assert status_of(session_factory, reservation_id) == PENDING_APPROVAL


def test_ve_03_8c_only_the_courts_venue_managers_and_admins_are_asked_to_approve(
    session_factory: sessionmaker,
) -> None:
    client = TestClient(app)
    user_id, token = make_user(session_factory, "player@example.com")
    own_manager, _ = make_user(
        session_factory, "own@example.com", UserRole.VENUE_MANAGER
    )
    outsider, _ = _manager_of_another_venue(session_factory, "outsider@example.com")
    admin, _ = make_user(session_factory, "admin@example.com", UserRole.ADMIN)
    court_id = make_court(session_factory, requires_approval=True)
    reservation_id = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(18),
        at(19),
        ReservationStatus.PENDING,
        hold_in_future(),
    )

    assert confirm(client, token, reservation_id).json()["status"] == "PENDING_APPROVAL"

    assert notification_types(session_factory, own_manager) == [
        NotificationType.APPROVAL_REQUESTED
    ]
    assert notification_types(session_factory, admin) == [
        NotificationType.APPROVAL_REQUESTED
    ]
    assert notification_types(session_factory, outsider) == []
