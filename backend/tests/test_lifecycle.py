"""Tests derived from the Reservation Lifecycle's detailed design
(docs/architecture-and-decisions.md § "C05 Detailed Design"). Each name
starts with the id of the DD test it runs (DD-T1…DD-T9, table in
docs/evidence-and-evolution.md § "C05 DD Verification Evidence").

DD-T1…DD-T6 are unit tests: the policy (`check_transition`,
`check_cancellable`) is pure, so they run on unsaved objects and an
injected clock, without a database. DD-T7…DD-T9 need the real session and
PostgreSQL row locks, so they are component/integration tests."""

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from test_spec_baseline import (
    add_reservation,
    at,
    bearer,
    cancel,
    event_types,
    hold_in_future,
    make_court,
    make_user,
    status_of,
)

from reservations import approval_service
from reservations.lifecycle import (
    ALLOWED_TRANSITIONS,
    GUARDS,
    Rejection,
    TransitionRejected,
    check_cancellable,
    check_transition,
    transition,
)
from reservations.main import app
from reservations.models import (
    Court,
    Notification,
    Reservation,
    ReservationEvent,
    ReservationEventType,
    ReservationStatus,
)

S = ReservationStatus
NOW = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
TICK = timedelta(microseconds=1)
ABSORBING = (S.COMPLETED, S.CANCELLED, S.EXPIRED, S.REJECTED, S.NO_SHOW)

# The oracle for DD-T1, written down from docs/specification.md BR-09 (the
# transition table) and §5.2 (the statechart), row by row — deliberately
# not derived from lifecycle.py, so the tests compare the code with the
# specification instead of with itself.
BR_09_EDGES: set[tuple[ReservationStatus, ReservationStatus]] = {
    (S.PENDING, S.CONFIRMED),
    (S.PENDING, S.PENDING_APPROVAL),
    (S.PENDING, S.CANCELLED),
    (S.PENDING, S.EXPIRED),
    (S.PENDING_APPROVAL, S.CONFIRMED),
    (S.PENDING_APPROVAL, S.REJECTED),
    (S.PENDING_APPROVAL, S.CANCELLED),
    (S.PENDING_APPROVAL, S.EXPIRED),
    (S.CONFIRMED, S.CANCELLED),
    (S.CONFIRMED, S.CHECKED_IN),
    (S.CONFIRMED, S.NO_SHOW),
    (S.CHECKED_IN, S.COMPLETED),
    (S.CHECKED_IN, S.CANCELLED),
}
# BR-09's guard column: the edges that have a guard in the specification
# (the fulfilment edges and the → CANCELLED edges have none in the Lifecycle).
BR_09_GUARDED_EDGES = {
    (S.PENDING, S.CONFIRMED),
    (S.PENDING, S.PENDING_APPROVAL),
    (S.PENDING, S.EXPIRED),
    (S.PENDING_APPROVAL, S.CONFIRMED),
    (S.PENDING_APPROVAL, S.REJECTED),
    (S.PENDING_APPROVAL, S.EXPIRED),
}


def unsaved(
    status: ReservationStatus,
    *,
    hold: datetime | None = None,
    approval: datetime | None = None,
    active: bool = True,
    requires_approval: bool = False,
) -> Reservation:
    """A reservation and its court that never touch a session — the policy
    must not need one."""
    start = NOW + timedelta(days=1)
    return Reservation(
        status=status,
        start_time=start,
        end_time=start + timedelta(hours=1),
        hold_expires_at=hold,
        approval_expires_at=approval,
        court=Court(active=active, requires_approval=requires_approval),
    )


def rejection(
    reservation: Reservation,
    target: ReservationStatus,
    *,
    decision: bool = False,
    now: datetime = NOW,
) -> Rejection | None:
    try:
        check_transition(reservation, target, approval_decision=decision, now=now)
    except TransitionRejected as exc:
        return exc.reason
    return None


# --------------------------------------------------------------------------- unit: the policy


@pytest.mark.parametrize("old", list(S))
@pytest.mark.parametrize("new", list(S))
def test_dd_t1_the_edge_table_is_checked_before_any_guard(
    old: ReservationStatus, new: ReservationStatus
) -> None:
    """Every one of the 9×9 (from, to) pairs: an edge outside BR-09 is
    ILLEGAL_TRANSITION whatever the guards would say; an edge inside it is
    never reported as illegal (a guard may still refuse it)."""
    reason = rejection(unsaved(old), new, decision=True)

    if (old, new) in BR_09_EDGES:
        assert reason != Rejection.ILLEGAL_TRANSITION
    else:
        assert reason == Rejection.ILLEGAL_TRANSITION


def test_dd_t1_absorbing_states_and_the_guard_table_agree_with_br_09() -> None:
    code_edges = {
        (old, new) for old, targets in ALLOWED_TRANSITIONS.items() for new in targets
    }
    assert code_edges == BR_09_EDGES
    assert all(ALLOWED_TRANSITIONS[state] == set() for state in ABSORBING)
    # One guard row per guarded BR-09 edge, and no other: a row for an edge
    # the table doesn't allow would be dead code pretending to be a rule.
    assert set(GUARDS) == BR_09_GUARDED_EDGES


@pytest.mark.parametrize(
    ("hold_lapsed", "active", "requires_approval", "to_confirmed", "to_submitted"),
    [
        (False, True, False, None, Rejection.APPROVAL_NOT_REQUIRED),
        (False, True, True, Rejection.APPROVAL_REQUIRED, None),
        (False, False, False, Rejection.COURT_INACTIVE, Rejection.COURT_INACTIVE),
        (False, False, True, Rejection.COURT_INACTIVE, Rejection.COURT_INACTIVE),
        (True, True, False, Rejection.HOLD_EXPIRED, Rejection.HOLD_EXPIRED),
        (True, True, True, Rejection.HOLD_EXPIRED, Rejection.HOLD_EXPIRED),
        (True, False, False, Rejection.HOLD_EXPIRED, Rejection.HOLD_EXPIRED),
        (True, False, True, Rejection.HOLD_EXPIRED, Rejection.HOLD_EXPIRED),
    ],
)
def test_dd_t2_confirm_decision_table(
    hold_lapsed: bool,
    active: bool,
    requires_approval: bool,
    to_confirmed: Rejection | None,
    to_submitted: Rejection | None,
) -> None:
    """The full PENDING → CONFIRMED / PENDING_APPROVAL decision table: all
    8 combinations of the three conditions, guard order hold → court →
    approval flag, so exactly one target is reachable from a live hold on
    an active court (BR-09, BR-11)."""
    hold = NOW - TICK if hold_lapsed else NOW + timedelta(minutes=5)
    reservation = unsaved(
        S.PENDING, hold=hold, active=active, requires_approval=requires_approval
    )

    assert rejection(reservation, S.CONFIRMED) == to_confirmed
    assert rejection(reservation, S.PENDING_APPROVAL) == to_submitted


@pytest.mark.parametrize(
    ("field", "alive_target", "lapsed_target", "dead_reason", "alive_reason"),
    [
        (
            "hold",
            S.CONFIRMED,
            S.EXPIRED,
            Rejection.HOLD_EXPIRED,
            Rejection.HOLD_NOT_EXPIRED,
        ),
        (
            "approval",
            S.REJECTED,
            S.EXPIRED,
            Rejection.APPROVAL_EXPIRED,
            Rejection.APPROVAL_NOT_EXPIRED,
        ),
    ],
)
def test_dd_t3_a_deadline_is_alive_at_its_own_instant_and_dead_one_tick_later(
    field: str,
    alive_target: ReservationStatus,
    lapsed_target: ReservationStatus,
    dead_reason: Rejection,
    alive_reason: Rejection,
) -> None:
    """BR-06 / BR-12: expired iff `deadline < now`. The two edges out of a
    deadline (act on it / expire it) are exact complements at every
    instant, so a reservation is never both actionable and expirable."""
    status = S.PENDING if field == "hold" else S.PENDING_APPROVAL
    reservation = unsaved(status, **{field: NOW})
    # Confirm takes no decision; Reject does (NOT_AWAITING_APPROVAL otherwise).
    decision = field == "approval"

    assert rejection(reservation, alive_target, decision=decision, now=NOW) is None
    assert rejection(reservation, lapsed_target, now=NOW) == alive_reason

    later = NOW + TICK
    assert (
        rejection(reservation, alive_target, decision=decision, now=later)
        == dead_reason
    )
    assert rejection(reservation, lapsed_target, now=later) is None


def test_dd_t4_only_a_live_manager_decision_ends_an_approval_request() -> None:
    open_request = unsaved(S.PENDING_APPROVAL, approval=NOW + timedelta(hours=1))
    lapsed_request = unsaved(S.PENDING_APPROVAL, approval=NOW - TICK)
    inactive_court = unsaved(
        S.PENDING_APPROVAL, approval=NOW + timedelta(hours=1), active=False
    )

    # BR-11: no decision, no CONFIRMED/REJECTED — checked first, so a
    # non-manager learns nothing about the request's deadline.
    assert rejection(open_request, S.CONFIRMED) == Rejection.DECISION_REQUIRED
    assert rejection(lapsed_request, S.REJECTED) == Rejection.DECISION_REQUIRED
    assert rejection(open_request, S.CONFIRMED, decision=True) is None
    # BR-12: an expired request can be neither approved nor rejected.
    assert (
        rejection(lapsed_request, S.CONFIRMED, decision=True)
        == Rejection.APPROVAL_EXPIRED
    )
    # A closed court can't be approved onto, but it can still be refused.
    assert (
        rejection(inactive_court, S.CONFIRMED, decision=True)
        == Rejection.COURT_INACTIVE
    )
    assert rejection(inactive_court, S.REJECTED, decision=True) is None
    # OP-05/OP-06 precondition: a decision applies only to a request. On a
    # normal court a live PENDING hold passes every PENDING -> CONFIRMED
    # guard, so this is the only thing stopping Approve from confirming it.
    live_hold = unsaved(S.PENDING, hold=NOW + timedelta(minutes=5))
    assert rejection(live_hold, S.CONFIRMED) is None
    assert (
        rejection(live_hold, S.CONFIRMED, decision=True)
        == Rejection.NOT_AWAITING_APPROVAL
    )
    # Grandfathering (BR-11): the flag is off on all three courts here, and
    # the request is still decidable — no approval-flag guard on these edges.


@pytest.mark.parametrize("state", list(S))
def test_dd_t5_cancel_policy_by_state_and_time(state: ReservationStatus) -> None:
    reservation = unsaved(state)
    start = reservation.start_time

    if state in (S.PENDING, S.PENDING_APPROVAL, S.CONFIRMED):
        check_cancellable(reservation, now=start - TICK)  # does not raise
        with pytest.raises(TransitionRejected) as started:
            check_cancellable(reservation, now=start)
        assert started.value.reason == Rejection.ALREADY_STARTED
    else:
        with pytest.raises(TransitionRejected) as refused:
            check_cancellable(reservation, now=start - timedelta(days=1))
        assert refused.value.reason == Rejection.NOT_CANCELLABLE


def test_dd_t6_a_rejection_is_a_409_with_a_reason_and_the_api_wording() -> None:
    """The contract every caller relies on: a 409 HTTPException (so routes
    need no mapping, and the worker's tick logs and moves on), a machine
    reason, and the detail text the frontend already shows."""
    with pytest.raises(TransitionRejected) as exc_info:
        check_transition(unsaved(S.PENDING, hold=NOW - TICK), S.CONFIRMED, now=NOW)

    assert isinstance(exc_info.value, HTTPException)
    assert exc_info.value.status_code == 409
    assert exc_info.value.reason == Rejection.HOLD_EXPIRED
    assert exc_info.value.detail == "This hold has expired — book the slot again"

    with pytest.raises(TransitionRejected) as illegal:
        check_transition(unsaved(S.COMPLETED), S.CONFIRMED, now=NOW)
    assert illegal.value.detail == "Cannot move a COMPLETED reservation to CONFIRMED"


# --------------------------------------------------------------------------- component: transition() in a session


def test_dd_t7_transition_postconditions_and_all_or_nothing(
    session_factory: sessionmaker,
) -> None:
    """Success: status, deadlines and exactly one mapped event change
    together. Failure: nothing changes and no event is added — the caller
    can let the transaction roll back without cleaning up."""
    user_id, _ = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory, requires_approval=True)
    held = add_reservation(
        session_factory, court_id, user_id, at(10), at(11), S.PENDING, hold_in_future()
    )
    deadline = datetime.now(timezone.utc) + timedelta(hours=2)
    request = add_reservation(
        session_factory,
        court_id,
        user_id,
        at(12),
        at(13),
        S.PENDING_APPROVAL,
        approval_expires_at=deadline,
    )

    with session_factory() as session:
        reservation = session.get(Reservation, held, with_for_update=True)
        with pytest.raises(TransitionRejected):
            transition(session, reservation, S.CONFIRMED, actor_id=user_id)
        assert reservation.status == S.PENDING
        assert reservation.hold_expires_at is not None
        assert not [o for o in session.new if isinstance(o, ReservationEvent)]

        transition(session, reservation, S.PENDING_APPROVAL, actor_id=user_id, note="n")
        assert (reservation.status, reservation.hold_expires_at) == (
            S.PENDING_APPROVAL,
            None,
        )

        decided = session.get(Reservation, request, with_for_update=True)
        transition(session, decided, S.CONFIRMED, approval_decision=True)
        assert (decided.status, decided.approval_expires_at) == (S.CONFIRMED, None)
        session.commit()

    with session_factory() as session:
        submitted = session.scalars(
            select(ReservationEvent).where(ReservationEvent.reservation_id == held)
        ).one()
    assert (submitted.event_type, submitted.actor_id, submitted.note) == (
        ReservationEventType.SUBMITTED,
        user_id,
        "n",
    )
    assert event_types(session_factory, request) == [ReservationEventType.CONFIRMED]


def test_dd_t8_approval_workflow_cannot_submit_on_a_court_without_approval(
    session_factory: sessionmaker,
) -> None:
    """Collaboration Approval Workflow → Lifecycle: the workflow only
    *requests* PENDING_APPROVAL; the Lifecycle owns the BR-09 guard "court
    requires approval", so a wrong request leaves no deadline and tells
    nobody."""
    user_id, _ = make_user(session_factory, "u@example.com")
    court_id = make_court(session_factory, requires_approval=False)
    held = add_reservation(
        session_factory, court_id, user_id, at(10), at(11), S.PENDING, hold_in_future()
    )

    with session_factory() as session:
        reservation = session.get(Reservation, held, with_for_update=True)
        with pytest.raises(TransitionRejected) as exc_info:
            approval_service.submit_for_approval(session, reservation, actor_id=user_id)
        assert exc_info.value.reason == Rejection.APPROVAL_NOT_REQUIRED
        assert reservation.approval_expires_at is None
        assert not [o for o in session.new if isinstance(o, Notification)]

    assert status_of(session_factory, held) == S.PENDING


def check_in(client: TestClient, token: str, reservation_id: uuid.UUID):
    return client.post(
        f"/reservations/{reservation_id}/check-in", headers=bearer(token)
    )


def test_dd_t9_check_in_racing_cancel_has_exactly_one_winner(
    session_factory: sessionmaker,
) -> None:
    """The precondition "caller holds the row lock" (REQ-07) on the one
    route that didn't take it. Without the lock, a check-in that read
    CONFIRMED before a Cancel committed overwrote it: both 200, final state
    CHECKED_IN, a CANCELLED event in the history."""
    user_id, token = make_user(session_factory, "u@example.com")

    for round_number in range(20):
        court_id = make_court(session_factory, f"Race Court {round_number}")
        reservation_id = add_reservation(
            session_factory, court_id, user_id, at(18), at(19), S.CONFIRMED
        )
        barrier = threading.Barrier(2)
        codes: dict[str, int] = {}

        def call(name: str, action) -> None:
            client = TestClient(app, raise_server_exceptions=False)
            barrier.wait()
            codes[name] = action(client, token, reservation_id).status_code

        threads = [
            threading.Thread(target=call, args=("check_in", check_in)),
            threading.Thread(target=call, args=("cancel", cancel)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(codes.values()) == [200, 409], (round_number, codes)
        winner = S.CHECKED_IN if codes["check_in"] == 200 else S.CANCELLED
        assert status_of(session_factory, reservation_id) == winner, round_number
        assert event_types(session_factory, reservation_id) == [
            ReservationEventType(winner.value)
        ], round_number
