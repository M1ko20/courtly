"""The reservation state machine. Every status change — user-driven or from
the background worker — goes through `transition()` so illegal jumps
(e.g. COMPLETED -> CONFIRMED) are rejected and every change leaves an
audit trail in reservation_events.

Detailed design: docs/architecture-and-decisions.md § "C05 Detailed Design".
The decision is two tables, read in order: `ALLOWED_TRANSITIONS` (is the
edge in BR-09 at all?) and `GUARDS` (the BR-09 guard column for that edge,
first failing guard wins). A rule change is a change to one of them."""

import enum
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from reservations import payments
from reservations.models import (
    Reservation,
    ReservationEvent,
    ReservationEventType,
    ReservationStatus,
)

ALLOWED_TRANSITIONS: dict[ReservationStatus, set[ReservationStatus]] = {
    ReservationStatus.PENDING: {
        ReservationStatus.CONFIRMED,
        ReservationStatus.PENDING_APPROVAL,
        ReservationStatus.CANCELLED,
        ReservationStatus.EXPIRED,
    },
    ReservationStatus.PENDING_APPROVAL: {
        ReservationStatus.CONFIRMED,
        ReservationStatus.REJECTED,
        ReservationStatus.CANCELLED,
        ReservationStatus.EXPIRED,
    },
    # No CONFIRMED -> COMPLETED: a slot that ended without a check-in is a
    # NO_SHOW (BR-09, spec §5.2); only CHECKED_IN completes.
    ReservationStatus.CONFIRMED: {
        ReservationStatus.CHECKED_IN,
        ReservationStatus.CANCELLED,
        ReservationStatus.NO_SHOW,
    },
    ReservationStatus.CHECKED_IN: {
        ReservationStatus.COMPLETED,
        ReservationStatus.CANCELLED,
    },
    ReservationStatus.COMPLETED: set(),
    ReservationStatus.CANCELLED: set(),
    ReservationStatus.EXPIRED: set(),
    ReservationStatus.REJECTED: set(),
    ReservationStatus.NO_SHOW: set(),
}

# BR-03: the only states a user-facing Cancel may start from. The wider
# ALLOWED_TRANSITIONS table above still lets a facility block cancel a
# CHECKED_IN reservation — that is a venue action, not a Cancel.
CANCELLABLE_STATUSES = (
    ReservationStatus.PENDING,
    ReservationStatus.PENDING_APPROVAL,
    ReservationStatus.CONFIRMED,
)

_EVENT_FOR_STATUS: dict[ReservationStatus, ReservationEventType] = {
    ReservationStatus.PENDING_APPROVAL: ReservationEventType.SUBMITTED,
    ReservationStatus.REJECTED: ReservationEventType.REJECTED,
    ReservationStatus.CONFIRMED: ReservationEventType.CONFIRMED,
    ReservationStatus.CHECKED_IN: ReservationEventType.CHECKED_IN,
    ReservationStatus.COMPLETED: ReservationEventType.COMPLETED,
    ReservationStatus.CANCELLED: ReservationEventType.CANCELLED,
    ReservationStatus.EXPIRED: ReservationEventType.EXPIRED,
    ReservationStatus.NO_SHOW: ReservationEventType.NO_SHOW,
}


class Rejection(enum.StrEnum):
    """Why the Lifecycle refused a transition — one value per guard, so a
    test (or a caller) can tell the reasons apart without parsing text."""

    ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
    HOLD_EXPIRED = "HOLD_EXPIRED"
    HOLD_NOT_EXPIRED = "HOLD_NOT_EXPIRED"
    COURT_INACTIVE = "COURT_INACTIVE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_NOT_REQUIRED = "APPROVAL_NOT_REQUIRED"
    DECISION_REQUIRED = "DECISION_REQUIRED"
    NOT_AWAITING_APPROVAL = "NOT_AWAITING_APPROVAL"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_NOT_EXPIRED = "APPROVAL_NOT_EXPIRED"
    NOT_CANCELLABLE = "NOT_CANCELLABLE"
    ALREADY_STARTED = "ALREADY_STARTED"


_MESSAGES: dict[Rejection, str] = {
    Rejection.HOLD_EXPIRED: "This hold has expired — book the slot again",
    Rejection.HOLD_NOT_EXPIRED: "This hold has not expired yet",
    Rejection.COURT_INACTIVE: "This court is no longer available",
    Rejection.APPROVAL_REQUIRED: "This court requires a venue manager's approval",
    Rejection.APPROVAL_NOT_REQUIRED: "This court does not require approval",
    Rejection.DECISION_REQUIRED: "Only a venue manager's decision can do that",
    Rejection.NOT_AWAITING_APPROVAL: "This reservation is not awaiting approval",
    Rejection.APPROVAL_EXPIRED: "This approval request has expired",
    Rejection.APPROVAL_NOT_EXPIRED: "This approval request has not expired yet",
    Rejection.ALREADY_STARTED: (
        "This reservation has already started and can no longer be cancelled"
    ),
}


class TransitionRejected(HTTPException):
    """A refused transition: always 409, with the reason as a code. An
    HTTPException like every other rule check here (`rules.py`,
    `booking_validation.py`), so routes need no mapping of their own."""

    def __init__(self, reason: Rejection, detail: str | None = None) -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail or _MESSAGES[reason])
        self.reason = reason


def _lapsed(deadline: datetime | None, now: datetime) -> bool:
    """BR-06 / BR-12: a deadline has passed iff `deadline < now` — at the
    deadline instant itself the hold or request is still alive."""
    return deadline is not None and deadline < now


# A guard sees the reservation, the decision instant and whether the caller
# is a manager's Approve/Reject; it returns None to let the transition pass.
Guard = Callable[[Reservation, datetime, bool], Rejection | None]


def _hold_alive(r: Reservation, now: datetime, _: bool) -> Rejection | None:
    # Dead at its deadline even if the worker has not swept it yet (BR-06).
    return Rejection.HOLD_EXPIRED if _lapsed(r.hold_expires_at, now) else None


def _hold_lapsed(r: Reservation, now: datetime, _: bool) -> Rejection | None:
    return None if _lapsed(r.hold_expires_at, now) else Rejection.HOLD_NOT_EXPIRED


def _court_active(r: Reservation, _now: datetime, _: bool) -> Rejection | None:
    return None if r.court.active else Rejection.COURT_INACTIVE


def _no_approval_needed(r: Reservation, _now: datetime, _: bool) -> Rejection | None:
    # BR-11: on an approval-required court CONFIRMED is reachable through Approve alone.
    return Rejection.APPROVAL_REQUIRED if r.court.requires_approval else None


def _approval_needed(r: Reservation, _now: datetime, _: bool) -> Rejection | None:
    return None if r.court.requires_approval else Rejection.APPROVAL_NOT_REQUIRED


def _manager_decision(
    _r: Reservation, _now: datetime, decision: bool
) -> Rejection | None:
    # Only Approve/Reject (which check the venue-manager role) pass a decision.
    return None if decision else Rejection.DECISION_REQUIRED


def _request_alive(r: Reservation, now: datetime, _: bool) -> Rejection | None:
    return Rejection.APPROVAL_EXPIRED if _lapsed(r.approval_expires_at, now) else None


def _request_lapsed(r: Reservation, now: datetime, _: bool) -> Rejection | None:
    if _lapsed(r.approval_expires_at, now):
        return None
    return Rejection.APPROVAL_NOT_EXPIRED


# BR-09's guard column, one row per guarded edge, checked in this order. An
# edge in ALLOWED_TRANSITIONS without a row here has no guard in the
# Lifecycle: Cancel's BR-03 is the operation's (`check_cancellable`), because
# a facility block may cancel without it; fulfilment edges are outside the
# baseline (§9).
GUARDS: dict[tuple[ReservationStatus, ReservationStatus], tuple[Guard, ...]] = {
    (ReservationStatus.PENDING, ReservationStatus.CONFIRMED): (
        _hold_alive,
        _court_active,
        _no_approval_needed,
    ),
    (ReservationStatus.PENDING, ReservationStatus.PENDING_APPROVAL): (
        _hold_alive,
        _court_active,
        _approval_needed,
    ),
    (ReservationStatus.PENDING, ReservationStatus.EXPIRED): (_hold_lapsed,),
    (ReservationStatus.PENDING_APPROVAL, ReservationStatus.CONFIRMED): (
        _manager_decision,
        _request_alive,
        _court_active,
    ),
    (ReservationStatus.PENDING_APPROVAL, ReservationStatus.REJECTED): (
        _manager_decision,
        _request_alive,
    ),
    (ReservationStatus.PENDING_APPROVAL, ReservationStatus.EXPIRED): (_request_lapsed,),
}


def check_transition(
    reservation: Reservation,
    new_status: ReservationStatus,
    *,
    approval_decision: bool = False,
    now: datetime | None = None,
) -> None:
    """Decide whether `reservation` may move to `new_status` now. Pure: reads
    the reservation and its court, changes nothing; raises TransitionRejected."""
    now = now or datetime.now(timezone.utc)
    old_status = reservation.status
    if new_status not in ALLOWED_TRANSITIONS[old_status]:
        raise TransitionRejected(
            Rejection.ILLEGAL_TRANSITION,
            f"Cannot move a {old_status} reservation to {new_status}",
        )
    # OP-05/OP-06 precondition: a manager's decision is taken only on a
    # PENDING_APPROVAL request. Without this, Approve on a normal court's
    # PENDING hold would pass the PENDING -> CONFIRMED guards (VE-05.3).
    if approval_decision and old_status != ReservationStatus.PENDING_APPROVAL:
        raise TransitionRejected(Rejection.NOT_AWAITING_APPROVAL)
    for guard in GUARDS.get((old_status, new_status), ()):
        reason = guard(reservation, now, approval_decision)
        if reason is not None:
            raise TransitionRejected(reason)


def check_cancellable(reservation: Reservation, now: datetime | None = None) -> None:
    """BR-03 (state + time part): cancellable only while PENDING,
    PENDING_APPROVAL or CONFIRMED and strictly before the start instant. Ownership is checked by the caller."""
    now = now or datetime.now(timezone.utc)
    if reservation.status not in CANCELLABLE_STATUSES:
        raise TransitionRejected(
            Rejection.NOT_CANCELLABLE,
            f"Cannot cancel a {reservation.status} reservation",
        )
    if now >= reservation.start_time:
        raise TransitionRejected(Rejection.ALREADY_STARTED)


def transition(
    db: Session,
    reservation: Reservation,
    new_status: ReservationStatus,
    actor_id: uuid.UUID | None = None,
    note: str | None = None,
    *,
    approval_decision: bool = False,
    now: datetime | None = None,
) -> None:
    """Check, then perform: status, deadlines, audit event, payment release —
    all in the caller's transaction, or none of it if the check fails.

    `approval_decision=True` is passed only by Approve/Reject, after they
    have checked the caller is a venue manager (BR-10, BR-11). `now` is the
    decision instant; the worker passes the one its sweep selected with.

    Concurrency contract (not enforced here — see docs/capability-map.md):
    the caller must already hold a row lock on `reservation` (`SELECT ...
    FOR UPDATE`, e.g. `_get_owned_reservation(..., lock=True)` in
    `api/reservations.py`, or a `.with_for_update()`-selected row as in
    `worker.py`/`facility_blocks.py`) before calling this. Every call site
    in this codebase does; a new one that doesn't would silently reopen the
    race two concurrent transitions on the same reservation would otherwise
    hit — this function only checks the state-machine edge, not isolation.
    """
    check_transition(
        reservation, new_status, approval_decision=approval_decision, now=now
    )

    reservation.status = new_status
    if new_status in (ReservationStatus.CONFIRMED, ReservationStatus.PENDING_APPROVAL):
        reservation.hold_expires_at = None
    if new_status != ReservationStatus.PENDING_APPROVAL:
        # Whether approved, rejected, cancelled or expired, no approval is pending any more.
        reservation.approval_expires_at = None

    db.add(
        ReservationEvent(
            reservation_id=reservation.id,
            event_type=_EVENT_FOR_STATUS[new_status],
            actor_id=actor_id,
            note=note,
        )
    )
    # Every path that releases a reservation passes here, so a refund can't
    # be forgotten by one of them (ADR-010). It only queues; no I/O.
    payments.release_for(db, reservation)
