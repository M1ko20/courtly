# C01 Engineering Spike

**Variant:** A — Persistence · **Date:** 2026-09-14 · **Branch:** `c01-spike`

Question / unknown:
Can we save a Reservation to a real PostgreSQL database and load it back unchanged, including time-zone-aware slot times, the state enum and references to Court and User?
And can the database itself enforce the common rule, "CONFIRMED reservations of the same court must not overlap", even when many players confirm the same slot at the same time (our Q future pressure)? Or do we need application-level locking?

What we did:
- Modelled `Court`, `User` and `Reservation` in SQLAlchemy 2 (`backend/src/reservations/models/`), with states `DRAFT / CONFIRMED / CANCELLED` stored as a PostgreSQL enum and `start_time`/`end_time` as `timestamptz`.
- Added a PostgreSQL exclusion constraint (needs the `btree_gist` extension). It rejects two CONFIRMED rows for the same court whose half-open ranges `[start, end)` overlap.
- Started a real PostgreSQL 16 with `docker compose up -d --wait db` and ran `uv run pytest -v -s`. The tests are in `backend/tests/test_persistence_spike.py`:
  1. `test_reservation_roundtrip`: saves a CONFIRMED reservation for 18:00–19:30 Europe/Prague and reads it back in a new session. It checks id, court/user FK, status, and that the times are tz-aware and the same instant.
  2. `test_db_rejects_overlapping_confirmed`: 18:00–19:30 CONFIRMED, then 19:00–20:00 CONFIRMED on the same court must fail. An overlapping DRAFT and a back-to-back CONFIRMED (19:30–21:00) must be accepted.
  3. `test_concurrent_confirmations_only_one_wins`: 10 threads, each with its own DB connection, commit a CONFIRMED 18:00–19:00 on the same court at the same moment (synchronised with a `threading.Barrier`).

Observed result:
```
tests/test_health.py::test_health PASSED
tests/test_persistence_spike.py::test_reservation_roundtrip PASSED
tests/test_persistence_spike.py::test_db_rejects_overlapping_confirmed PASSED
tests/test_persistence_spike.py::test_concurrent_confirmations_only_one_wins
concurrent outcomes: ['ExclusionViolation' x9, 'ok' x1]
PASSED
======================== 4 passed, 2 warnings in 2.54s =========================
```
Constraint as created in the database (`pg_get_constraintdef`, PostgreSQL 16.15):
```
no_overlapping_confirmed_reservations | EXCLUDE USING gist (court_id WITH =, tstzrange(start_time, end_time, '[)'::text) WITH &&) WHERE ((status = 'CONFIRMED'::reservation_status))
reservation_time_order                | CHECK ((end_time > start_time))
```
- The round trip works. Times come back tz-aware (as UTC from PostgreSQL) and equal to the stored instant, so we must compare instants and not wall-clock strings.
- The overlapping CONFIRMED insert fails with `psycopg.errors.ExclusionViolation` (wrapped in SQLAlchemy `IntegrityError`). Overlapping DRAFT and back-to-back slots are accepted.
- Under 10 concurrent confirmations exactly **1 succeeded and 9 were rejected** by the database. No overlap got through, without any application-level locking.
- The 2 warnings are third-party deprecation notices (starlette/anyio in `TestClient`), unrelated to the spike.

Decision / what changes because of the result:
- **The common overlap rule is enforced in PostgreSQL by the exclusion constraint** (ADR-001). Application code may still pre-check availability for nicer error messages, but that check is never the only guard.
- The confirm endpoint (C02+) will catch `IntegrityError` with `ExclusionViolation` and map it to **HTTP 409 Conflict** ("slot already taken").
- We stay on **PostgreSQL for tests** (docker compose) and do not use SQLite, because SQLite has no exclusion constraints or `tstzrange`.
- Times are stored as `timestamptz` and handled as tz-aware `datetime` everywhere. The domain slot rule (07:00–22:00, :00/:30) will be evaluated in venue local time `Europe/Prague`.
- Next open point: the schema is created with `create_all`, so we need migrations (Alembic) before the first schema change. That ties into Release/Operation.

---

## Evidence C02: specifikace → běžící aplikace (specification → running application)

**Environment of the runs below:** PostgreSQL **16.15** (Homebrew, private cluster on port 55432 — Docker is not installed on the machine that produced this evidence, so `docker compose up -d db` was not used; the version is the one ADR-001 names), Python 3.12, `uv` 0.12.17, real background worker (not a test double). Every number below was produced in this session; nothing is copied from an earlier run.

### Přijatá baseline (accepted baseline)
| Baseline | Document | Status |
|---|---|---|
| **v0.1** — Create, Check Availability, Confirm, Cancel | [`specification-v0.1.md`](specification-v0.1.md) (frozen) | **Prepared for team approval** — the approval tick-boxes in its §11 are for the team; nothing here claims they were ticked |
| **v0.2** — v0.1 + approval process (Approve, Reject, expiry) | [`specification.md`](specification.md) | Prepared for team approval, same rule |

Both went through the nine-question acceptance review (§6 of each), the consistency review (§7), and carry an explicit decision register (D-01…D-20), assumptions (A-01…A-06) and unknowns.

### Předvedené základní operace (operations demonstrated)
All four operations run against the live API, each with a success case and a negative/boundary case (v0.1 run, executed again on top of the v0.2 code to prove nothing regressed — 20 of 20 checks as expected; a first run of the same script on the v0.1 code gave the same result):

```
# day under test: 2026-09-26 (Europe/Prague), court: Badminton Court 2

## OP-02 Check Availability (before anything is booked)
OK VE-02.x   expected 200      got 200 {'available': True, 'reason': None}

## OP-01 Create Reservation
OK VE-01.1   expected 201      got 201 {'id': '…', 'status': 'PENDING', 'hold_expires_at': '…'}
OK VE-01.7   expected 409      got 409  detail='This slot is currently held or booked by someone else — …'
OK VE-01.7b  expected 201      got 201 {'status': 'PENDING'}
OK VE-01.2   expected 422      got 422  detail='Value error, end_time must be after start_time'
OK VE-01.4   expected 401      got 401  detail='Not authenticated'
OK VE-01.5   expected 422      got 422  detail='Value error, reservation must lie within opening hours 07:00-22:00'

## OP-02 Check Availability (after the hold)
OK VE-02.2   expected 200      got 200 {'available': False, 'reason': 'RESERVATION_OVERLAP'}
OK VE-02.1   expected 200      got 200 {'available': True, 'reason': None}
OK VE-02.6   expected 422      got 422  detail='Value error, reservation must be 60, 90 or 120 minutes long'
OK VE-02.6b  expected 404      got 404  detail='Court not found'

## OP-03 Confirm Reservation
OK VE-03.5   expected 403      got 403  detail='Not your reservation'
OK VE-03.1   expected 200      got 200 {'status': 'CONFIRMED', 'hold_expires_at': None}
OK VE-03.2   expected 409      got 409  detail='Cannot move a CONFIRMED reservation to CONFIRMED'
OK VE-03.3   expected 409      got 409  detail='This hold has expired — book the slot again'
   status of the expired hold right after the rejected confirm: PENDING  (blocked: True)
   after 16s the server's own worker swept it -> EXPIRED; interval available again: True

## OP-04 Cancel Reservation
OK VE-04.1   expected 200      got 200 {'status': 'CANCELLED'}
   interval free again after cancel: True
OK VE-04.5   expected 409      got 409  detail='Cannot cancel a CANCELLED reservation'
OK VE-04.6   expected 403      got 403  detail='Not your reservation'
OK VE-04.2   expected 200      got 200 {'status': 'CANCELLED'}
OK VE-04.3   expected 409      got 409  detail='This reservation has already started and can no longer be cancelled'
   the started reservation is still: CONFIRMED
```

### Skutečně provedené příklady ověření (verification examples actually run)
| Where | What | Result |
|---|---|---|
| `backend/tests/test_spec_baseline.py` | every VE-01…VE-04 of v0.1 (43 test cases, incl. 8-way concurrent Create, 20× Confirm‖Cancel race, boundary tests with an injected clock) | 43 passed |
| `backend/tests/test_approval_api.py` | every VE of the v0.2 additions (approve, reject, expiry, delay, no-bypass, races, drift guards; 37 test cases) | 37 passed |
| whole backend suite | the 96 pre-existing tests + the two files above | **176 passed** (real PostgreSQL 16.15) |
| mutation check | seven guards deliberately broken in a scratch copy (BR-11 guard, approval-decision flag, blocking-state set, waitlist bypass, row lock, reschedule guard, reschedule lock) | each broken guard made the intended test(s) fail |
| frontend | `npm run build` (`tsc -b` + Vite) and `npm run lint` | build passes; lint shows only warnings that were there before. **The UI was not exercised in a browser in this session.** |

The v0.2 flows were also run live, including the real worker expiring an undecided request (the request that was *not* past its deadline stayed `PENDING_APPROVAL` through the same cycles — the "delay" case):

```
# day under test: 2026-09-27 (Europe/Prague); approval-required court = Tennis Court 2, normal court = Badminton Court 2

## Normal court is unchanged (v0.1 behaviour)
OK VE-03.8b  expected 200  got 200 {'status': 'CONFIRMED'}

## OP-03 Confirm on an approval-required court = submission
OK VE-03.8   expected 200  got 200 {'status': 'PENDING_APPROVAL', 'hold_expires_at': None, 'approval_expires_at': '+24 h'}
   slot still blocked: True; another player asking for it: OK VE-01.7   expected 409  got 409  detail='This slot is currently held or booked by someone else — …'
   manager notifications now include 'Approval needed': True
OK VE-03.10  expected 409  got 409  detail="Only a venue manager's decision can do that"

## OP-05 Approve
OK VE-05.2   expected 403  got 403  detail='Venue manager access required'
OK VE-05.1   expected 200  got 200 {'status': 'CONFIRMED', 'approval_expires_at': None}
   slot after approval still blocked: True
OK VE-05.3   expected 409  got 409  detail='Cannot move a CONFIRMED reservation to CONFIRMED'
OK VE-05.7   expected 409  got 409  detail='This court requires approval — cancel this reservation and request the new time instead'

## OP-06 Reject
OK VE-06.2   expected 403  got 403  detail='Venue manager access required'
OK VE-06.1   expected 200  got 200 {'status': 'REJECTED'}
   slot released: True; player notified: True
OK VE-06.3   expected 409  got 409  detail='Cannot move a REJECTED reservation to REJECTED'
OK VE-06.5   expected 201  got 201 {'status': 'PENDING'}

## Cancel a request (OP-04)
OK VE-04.8   expected 200  got 200 {'status': 'CANCELLED'}
   slot released: True
OK VE-05.3b  expected 409  got 409  detail='Cannot move a CANCELLED reservation to CONFIRMED'

## Delay and expiry (REQ-10) — the server's own worker does the expiring
OK VE-05.4   expected 409  got 409  detail='This approval request has expired'
   right after: expiring request is still PENDING_APPROVAL (blocking: True)
   after 30s the worker swept it -> EXPIRED; slot released: True
   VE-07.2 the undecided request is untouched by the same cycles: PENDING_APPROVAL (blocking: True)
OK VE-07.1   expected 409  got 409  detail='Cannot move a EXPIRED reservation to CONFIRMED'
   audit trail of the expired request: ['CREATED', 'SUBMITTED', 'EXPIRED (Approval request expired undecided)']
```

### Nalezený nesoulad a způsob vyřešení (mismatches found, and which source was wrong)
The rule of the assignment — do not assume "the code is wrong" — was applied per mismatch. The tests of `test_spec_baseline.py` were written from the specification **before** the code was touched; **20 of 43 failed on the unmodified app** (13 because the availability verdict endpoint did not exist, 2 because the boundary logic could not be exercised with a clock, 5 because of genuine behaviour defects).

| # | Mismatch | Wrong source | Resolution |
|---|---|---|---|
| 1 | Project Frame / ADR-001 / the assignment's reference example: a non-blocking `DRAFT`, only `CONFIRMED` excluded. The app (deliberately) blocks with a 5-minute `PENDING` hold. | **Documents** — not the code | Decision D-01 written into the specification; ADR-001 amended; Project Frame and READMEs updated. No code change. Reference REQ-03/04 ("Confirm fails on overlap") rewritten: with D-01 Confirm cannot fail that way. |
| 2 | No interval verdict for Check Availability (only a day list of busy slots, ignoring facility blocks) | **Implementation gap** | `GET /courts/{id}/availability/check` added (VE-02.x). The day view remains a UI read model; its facility-block gap is recorded as G-01, not fixed here. |
| 3 | Confirm accepted a hold past its deadline (200 instead of 409) — VE-03.3 | **Implementation** | Guard in `lifecycle.py`. |
| 4 | Confirm accepted a deactivated court — VE-03.4 | **Implementation** | Same guard. |
| 5 | Cancel had no time boundary and allowed `CHECKED_IN`; the docs never defined a policy — VE-04.3 | **Specification was silent** → policy chosen (D-03), then implementation and UI aligned | `check_cancellable` (strictly before start; `PENDING`/`PENDING_APPROVAL`/`CONFIRMED`); the UI hides Cancel otherwise. |
| 6 | A naive `end_time` crashed with **HTTP 500** (`TypeError`), spec says 422 — VE-01.2b | **Implementation** | Validation in `validate_slot_shape`. |
| 7 | Concurrent Confirm and Cancel both returned 200 and the reservation ended `CONFIRMED` — a cancelled booking came back to life (lost update) — VE-03.6 | **Implementation** | Row lock (`SELECT … FOR UPDATE`) in the state-changing endpoints; the worker sweep skips locked rows. |
| 8 | v0.2, found by tracing every path to `CONFIRMED`: waitlist acceptance created `CONFIRMED` directly and reschedule moved an approved booking — both would bypass approval | **Design gap of the change**, found before implementing | BR-11 / REQ-11; guard inside the state machine; waitlist accept becomes `PENDING_APPROVAL`; reschedule refused for approved bookings (VE-05.7, VE-08.1, VE-08.2). |
| 9 | v0.2: the transition table alone would let the owner turn their own `PENDING_APPROVAL` into `CONFIRMED` via the ordinary Confirm endpoint | **Design gap**, closed while designing (a decision flag only Approve/Reject pass); not something a test found first | VE-03.10 verifies it. |
| 10 | v0.2: the calendar export silently mapped unknown statuses to `CONFIRMED`, so a request awaiting approval would have appeared as confirmed in the player's calendar | **Implementation** (found by sweeping every place that lists states) | Status map extended; test added. |
| 11 | Independent code review of the branch: the new approval notifications formatted the start time in the *server's* time zone instead of the venue's (known pitfall #1), and `reschedule` did not take the row lock the other state-changing endpoints do | **Implementation** (my own new code) | Notifications use `Europe/Prague`; reschedule locks the row (VE-05.7b, mutation-checked). Not changed, only noted: older notification texts use the same server-zone formatting, and waitlist acceptance does not check that the court is still active (both pre-date this work). |

### Shrnutí dopadu změny (change impact)
The change touched: BR-02/03/07/09/10 (extended), new BR-11/BR-12; REQ-04/06/07 changed, REQ-08…REQ-11 new; two new operations (Approve, Reject) for the *existing* Venue Manager actor; two new states (`PENDING_APPROVAL`, `REJECTED`); `EXPIRED` reused. Untouched: Create and Availability (their text), BR-01/04/05/06/08. New data: `courts.requires_approval`, `reservations.approval_expires_at`, three enum values ×2 → the dev database needs the drop/create/seed cycle. Full analysis, written before the specification: [`change-c02-impact.md`](change-c02-impact.md).

### Zbývající předpoklad / neznámá (remaining assumptions / unknowns)
- **Team approval of both baselines is still to be given** (tick-boxes in §11 of each specification).
  - *Update 2026-10-12:* given. The team approved v0.1, v0.2 and v0.3; see §11 of each specification.
- A-01 hold 5 min, A-05 approval window 24 h — product values without an external source, to be confirmed with the venue. A-06 no separation of duties.
- U-01 e-mail / external notification (Project Frame boundary) is not implemented; U-03 rejection reason text; U-04 re-approval instead of refusing to move an approved booking.
- G-01: the day-view availability ignores facility blocks (outside the baseline).
- Not verified: the UI in a browser; a run on the `docker compose` PostgreSQL (see the environment note).

### Architektonické drivery přenesené do C03 (architectural drivers carried into C03)
Details and code evidence in [`change-c02-impact.md`](change-c02-impact.md) §3. In short: **AD-1** a long-lived persisted time-bounded process (in-process 30 s polling worker, single-instance assumption); **AD-2** "which states block a court" is defined in four places (constraint, status tuple, availability, limits) — now only guarded by a drift test; **AD-3** row-level serialisation is load-bearing and lives in routers, not in one place; **AD-4** several doors to `CONFIRMED` (confirm, approve, waitlist accept); **AD-5** notifying a person who must act (in-app only, no delivery guarantees); **AD-6** authorisation beyond two roles.

### Commit / tag aplikace
Branch `feat/c02-spec-and-approval-flow` (merge commits keep these SHAs reachable). No tags — the repository has no tagging process (`versioning` skill); the SHAs identify the states:

| State | Commit |
|---|---|
| Baseline v0.1 specification | `4bb0239` |
| App conforming to v0.1 (5 fixes + verdict endpoint + 43 spec tests) | `76c99ba` |
| Change impact analysis (before any v0.2 edit) | `b5f1438` |
| Specification v0.2 | `b417cde` |
| App for v0.2 (backend + approval tests) | `a5345b5` |
| Frontend, docs and this evidence | the following commits of the same branch / pull request |

**Reproduce:**
```bash
docker compose up -d --wait db                      # or any PostgreSQL 16 with btree_gist
cd backend && uv sync
uv run pytest -v                                    # wipes the database it points at (see backend/CLAUDE.md)
uv run python -m reservations.seed                  # after the drop/create cycle for the new columns
uv run fastapi dev src/reservations/main.py         # Swagger at /docs; demo logins are printed by the seed
```

## C03 — Architecture Evidence

**Date:** 2026-10-05 · **Assignment:** `docs/course/C03.md` · **Full write-up:** `docs/architecture-and-decisions.md` § "C03 Part A" and § "C03 — Architecture"

Baseline: v0.2 (`docs/specification.md`). Scenario: OP-03 Confirm Reservation.

Part A: § "C03 Part A — AS-IS trace" (merged in PR #70). Runtime probe: while `notify()` was sending a Web Push during Confirm, a second DB session got `LockNotAvailable` on the reservation row and still saw `PENDING`, yet the API returned `200 CONFIRMED`. So the push was sent under the row lock, before commit.

Drivers: DR-1 lock scope / REQ-07 (AD-3); DR-2 notification after a business change, failure and retry (AD-5); DR-3 a single lifecycle decision owner (BR-09/11, AD-4); DR-4 long-lived approval state and time-driven transitions (BR-06/12, AD-1).

Decision question: where should the Web Push integration be isolated, and when (relative to the business transaction and its row lock) should a notification be delivered — what does a slow or failing push service mean for Confirm?

Alternatives: A — send after commit, synchronously, inside the request (no new state, no retry). B — transactional outbox (`push_deliveries`) + background dispatcher with retry.

Scenario walkthrough: Confirm on an approval-required court with a hanging push service and a concurrent Cancel (E3). Both alternatives keep state, BR-02/BR-11 and the in-app notification correct. A makes the Confirm response wait N managers × devices × 5 s and loses pushes on a crash or outage. B returns immediately and delivers at least once.

ADR: ADR-005 — chose B (`docs/architecture-and-decisions.md`).

Views (all Mermaid, all rendered with `@mermaid-js/mermaid-cli` without errors):
- domain class: C1
- context: G1
- static architecture: G2
- state ownership: G3 (table over the v0.2 statechart)
- runtime/deployment: G4
- design sequence: H1
- focused design class: H2

Cross-view issues found/resolved (I):
- R7/R8 (record vs. deliver a notification) had one owner → split into Inbox & Outbox and Push Delivery Integration.
- The dispatch loop had first been placed in the integration element → moved to the Scheduler (`worker.py` owns time-driven work).
- AS-IS `tick()` blocked the event loop → both loops now use `asyncio.to_thread`.
- R2: the API was defined as a requester and the Lifecycle as the decision owner (no code change; the guard is already authoritative).
- **Open:** waitlist accept creates `CONFIRMED`/`PENDING_APPROVAL` rows without going through the Lifecycle (`api/waitlist.py:115-122`). It is outside OP-03 and outside baseline §9, so it was not changed.

AS-IS → TO-BE delta (J): CHANGE for the push call site, the vendor SDK location, push failure handling and background loop execution. KEEP for the Confirm decision ownership, BR-02 (ADR-001) and the in-app row in the transaction. VERIFY for row-lock usage (passed) and "only Lifecycle changes status" (failed for waitlist accept, out of slice).

Implementation changes (`65aad78`):
- `models/push_delivery.py`: new outbox table.
- `notifications.py`: `notify()` only queues.
- `push_delivery.py`: dispatcher with retry/backoff; the only `pywebpush` import.
- `worker.py` / `main.py`: 5 s dispatch loop; both loops run via `asyncio.to_thread`.
- Tests: rewritten push tests plus `tests/test_architecture.py`.

Behaviour verification (PostgreSQL 16):
- `pytest tests/test_spec_baseline.py -k ve_03` → 9 passed (VE-03.1–03.7)
- `tests/test_approval_api.py` → 38 passed (VE-03.8–03.10, VE-05…)
- `-k "ve_03_6 or ve_01_9"` → 2 passed (concurrency)
- `tests/test_push_api.py` → 10 passed, including the commit-before-push boundary test and the retry → `FAILED` test
- full suite `uv run pytest` → **305 passed**
- Running app: Confirm `200 CONFIRMED` in 12 ms; within ~5 s the dispatcher attempted both queued pushes, recorded the (fake-key) error and scheduled a retry.

Architecture conformance rule + result: "only `push_delivery.py` may import `pywebpush`" — `backend/tests/test_architecture.py` (AST scan) → 2 passed. A mutation check (adding the import to `notifications.py`) made it fail as expected, and the change was reverted.

Remaining uncertainty / risk:
- Waitlist accept bypasses the Lifecycle (AD-4).
- Delivery is at least once (duplicate pushes are possible).
- `FAILED` deliveries are only visible in the database, and the outbox has no retention.
- Push latency is up to ~5 s.
- Single-process assumption for both loops (AD-1, ADR-004).
- The Part A spec gaps (mute, `ADMIN` as manager) are still open for the spec owners.
- C02 team sign-off of v0.2 is still open.
  - *Update 2026-10-12:* closed. The team approved v0.1, v0.2 and v0.3 (§11 of each specification).

Commit/tag: implementation `65aad78` and docs `38ef1a7` (branch `feat/c03-notification-outbox`), merged to `main` in PR #71 as merge commit `da3158d`. Tag **`c03-architecture`** points to `da3158d`.

### Follow-up 2026-10-08 — waitlist accept through the Lifecycle

This follow-up closes the first "Remaining uncertainty / risk" item above
("Waitlist accept bypasses the Lifecycle"). The rationale is in
`docs/architecture-and-decisions.md`, "Amendment (2026-10-08)".

- **Change:** `accept_waitlist_offer` creates a `PENDING` hold. It then
  calls `transition(…, CONFIRMED)` or `submit_for_approval`.
- **Behaviour verification:**
  - `test_accepted_offer_is_confirmed_through_the_lifecycle`: events are
    `CREATED` then `CONFIRMED`, and no hold deadline is left behind.
  - `test_offer_on_a_court_deactivated_meanwhile_cannot_be_accepted`:
    returns 409 and the offer stays `OFFERED`.
  - VE-08.1 (`PENDING_APPROVAL`, events `CREATED` then `SUBMITTED`) still
    passes.
  - Full suite: `uv run pytest` → **309 passed** (PostgreSQL 16).
- **Mutation check:** I put the old `api/waitlist.py` back temporarily.
  - The deactivated-court test failed, because the old code returned 200
    `CONFIRMED`.
  - The new architecture rule failed with
    `['api/waitlist.py:116 Reservation(status=...) not PENDING']`.
  - I then restored the fixed file.
- **Architecture conformance rule + result:** "only `lifecycle.transition()`
  changes a reservation's status".
  - Check: `backend/tests/test_architecture.py`
    `test_only_the_lifecycle_changes_reservation_status`, an AST scan,
    plus a self-test that the scan really detects a bypass.
  - Result: 4 passed.

## C05 DD Verification Evidence

**Date:** 2026-10-12 · **Assignment:** `docs/course/C05.md` · **Design:** `docs/architecture-and-decisions.md` § "C05 Detailed Design"

Unit: the Reservation Lifecycle (C03 G2, R2), `backend/src/reservations/lifecycle.py`.
Tests: `backend/tests/test_lifecycle.py`. Each test name starts with its DD id.

### Tests derived from DD

| DD element / decision | What must hold? | Test level | Test case |
|---|---|---|---|
| **DD-T1** interface contract: edge check before guards; `ALLOWED_TRANSITIONS` = BR-09 | For all 9 × 9 `(from, to)` pairs, an edge outside BR-09 is `ILLEGAL_TRANSITION` whatever the guards say, and an edge inside it never is. Absorbing states have no edges. Every `GUARDS` row is an allowed edge. | unit | `test_dd_t1_the_edge_table_is_checked_before_any_guard` (81 cases), `test_dd_t1_absorbing_states_and_the_guard_table_agree_with_br_09` |
| **DD-T2** algorithm branch: decision table for leaving a `PENDING` hold | All 8 combinations of hold lapsed × court active × requires approval give the tabled reason, with guard order hold → court → flag. From a live hold on an active court exactly one target is reachable. | unit | `test_dd_t2_confirm_decision_table` (8 cases) |
| **DD-T3** algorithm branch: `lapsed(d, now) = d < now` (BR-06, BR-12) | At `now = deadline` the hold/request is alive (act: yes, expire: `*_NOT_EXPIRED`). One microsecond later it is dead (act: `*_EXPIRED`, expire: yes). | unit | `test_dd_t3_a_deadline_is_alive_at_its_own_instant_and_dead_one_tick_later` (hold, approval) |
| **DD-T4** state transition guards out of `PENDING_APPROVAL` (BR-11, BR-12) | No decision → `DECISION_REQUIRED`, checked first. An expired request cannot be approved. An inactive court cannot be approved onto, but a request on it can still be rejected. *(Added 2026-11-02, C06 F1:)* a decision on a live `PENDING` hold → `NOT_AWAITING_APPROVAL`. | unit | `test_dd_t4_only_a_live_manager_decision_ends_an_approval_request` |
| **DD-T5** failure behaviour: `check_cancellable` (BR-03) | For every state: `PENDING`/`PENDING_APPROVAL`/`CONFIRMED` pass 1 µs before start and fail `ALREADY_STARTED` at start. Every other state fails `NOT_CANCELLABLE`. | unit | `test_dd_t5_cancel_policy_by_state_and_time` (9 cases) |
| **DD-T6** failure contract: `TransitionRejected` | It is an `HTTPException` with 409, it carries `reason`, and its `detail` is the wording the API already returned. | unit | `test_dd_t6_a_rejection_is_a_409_with_a_reason_and_the_api_wording` |
| **DD-T7** command postconditions, all-or-nothing | A refused `transition()` changes nothing and adds no event. A successful one sets the status, clears the right deadline and adds exactly one event of the mapped type with actor and note. | component (real session, PostgreSQL) | `test_dd_t7_transition_postconditions_and_all_or_nothing` |
| **DD-T8** collaboration Approval Workflow → Lifecycle | `submit_for_approval` on a court that doesn't require approval is refused by the Lifecycle's guard (`APPROVAL_NOT_REQUIRED`), with no deadline and no notifications. | component | `test_dd_t8_approval_workflow_cannot_submit_on_a_court_without_approval` |
| **DD-T9** concurrency precondition: the caller holds the row lock | Check-in racing Cancel on one `CONFIRMED` reservation, 20 rounds: exactly one gets 200 and the other 409, and the final state and the single event match the winner. | integration (HTTP, threads, PostgreSQL row locks) | `test_dd_t9_check_in_racing_cancel_has_exactly_one_winner` |

**DD-T2**
- **Selected level:** unit.
- **Why this level:** the decision is a pure function of three reservation and court attributes plus the clock (DD: `check_transition` has no side effects). A database would add nothing but setup time, and the whole table runs in milliseconds. The tests run on unsaved `Reservation`/`Court` objects with a fixed `now`. They pass with the test database URL pointed at a closed port, which shows they need no database.
- **What design decision does it verify?** The guard table `GUARDS` for the two `PENDING` exits and its order (hold → court → approval flag). Also that the new `PENDING → PENDING_APPROVAL` guard makes the two targets mutually exclusive (DR-3).

**DD-T7**
- **Selected level:** component.
- **Why this level:** the command's postconditions are about what it puts in the session (the event row, the deadline columns) and what a failing call leaves *out* of it. That needs a real `Session` and the real models. It still calls `transition()` directly instead of going through HTTP, so the API's own checks do not mask the unit.
- **What design decision does it verify?** "Check first, then mutate": a `TransitionRejected` is raised before any write. Also the effect rules: entering `PENDING_APPROVAL` clears the hold, and entering `CONFIRMED` clears the approval deadline, with one mapped event.

**DD-T9**
- **Selected level:** integration.
- **Why this level:** the property depends on PostgreSQL row locks and two real transactions interleaving. A unit test cannot show a missing lock.
- **What design decision does it verify?** That locking is the *caller's* precondition (the Lifecycle does not lock), and that every requester meets it.

### Unit/component tests executed

PostgreSQL 16, `cd backend`:

- `uv run pytest tests/test_lifecycle.py -k "t1 or t2 or t3 or t4 or t5 or t6"` → **103 passed in 0.69 s**.
- The same command with `TEST_DATABASE_URL=postgresql+psycopg://nobody:x@127.0.0.1:1/nowhere_test` (no database reachable) → **103 passed**.
- `uv run pytest tests/test_lifecycle.py tests/test_audit_log_api.py tests/test_payments_api.py tests/test_architecture.py` → **136 passed**. This includes DD-T7…T9 and the C03 architecture rules.
- **Mutation check for DD-T9:** I removed `lock=True` from `check_in_reservation` again and ran the test three times. It failed all three times in round 0, with `{'cancel': 200, 'check_in': 200}`. I then restored the lock.
- Full suite: `uv run pytest` → **487 passed** in 8 min 10 s.

### Design ↔ implementation mismatch

Planned DD vs. the code at the start (`main` at `49a7143`):

| DD decision | Implemented? (before) | Evidence | Action |
|---|---|---|---|
| Edge table = BR-09; edge check before guards | YES | `ALLOWED_TRANSITIONS`, unchanged; DD-T1 | keep |
| Guards as one ordered table, row for row BR-09's guard column | PARTLY: an `if` chain (`_check_guards`) covering 4 of the 6 guarded edges | old `lifecycle.py:87-142` | update code (`GUARDS`) |
| The Lifecycle guards the expiry edges (`deadline < now`) | **NO**: only the Scheduler's `WHERE … < now` query ensured it. `transition(…, EXPIRED)` on a live hold passed; two existing tests did exactly that | first full run after the change: those 2 failed, 485 passed | update code; both tests now ask for what is due (`test_audit_log_api.py` with a lapsed hold, `test_payments_api.py` at the worker's instant after the hold) |
| `PENDING → PENDING_APPROVAL` requires an approval court (BR-09 table) | **NO**: only the requesters' `if court.requires_approval` ensured it | DD-T8 | update code (`_approval_needed`) |
| A refusal carries a reason code | NO: `HTTPException(409, text)` | DD-T6 | update code (`Rejection`, `TransitionRejected`) |
| Decision instant injectable | PARTLY: `check_cancellable` had `now`, `_check_guards` read the wall clock | DD-T3 | update code; the worker passes its sweep instant |
| Refusal before any mutation; one event per change | YES | DD-T7 | keep (now tested directly) |
| Every requester holds the row lock (`transition()` precondition) | **PARTLY: check-in did not lock** | DD-T9 mutation run above | update code (`lock=True`, one line) |
| Approval deadline value owned by the Approval Workflow (C03 R5) | YES | `approval_service.submit_for_approval` | keep |
| Failure type independent of FastAPI | not adopted: the draft DD considered a framework-free exception plus a mapping in `main.py` | — | **update DD**: `TransitionRejected` subclasses `HTTPException`, the convention of `rules.py`/`booking_validation.py`; a second error mechanism for one module was not worth it |
| A hold ends when the reservation leaves `PENDING` (BR-06) | PARTLY: the column is cleared on entering `CONFIRMED`/`PENDING_APPROVAL` but kept on `CANCELLED`/`EXPIRED` | — | keep code, documented under "left to code": outside `PENDING` the value is history, not a hold in effect |

### Resolution

- **Code was wrong, fixed (4):**
  - Two BR-09 guards were enforced only by the requesters (expiry edges, submit on a normal court). The DD's decision that the Lifecycle owns *every* BR-09 guard (C03 DR-3) needed them inside the unit.
  - The check-in route broke `transition()`'s lock precondition, which allowed a real double outcome (the mutation run above).
  - There were no reason codes and no injectable clock.
- **DD was changed, not the code (1):** the error type. Matching the codebase convention outweighed framework independence for a module that only runs inside this one FastAPI process.
- **Docs were wrong (1):** `docs/capability-map.md` (2026-09-22) said every call site followed the lock convention. Check-in did not, and the row has been corrected.
- **No behaviour change for users:** same status codes and `detail` texts; every existing requester already met the two new guards.

### Remaining design risk

- **The lock precondition is still a convention.** A new requester without `lock=True` passes every unit test. Only a race test like DD-T9 catches it. Nothing in `transition()` can cheaply tell whether its own transaction holds the row lock.
- **Entering `PENDING_APPROVAL` and setting its deadline are two steps.** They happen in one transaction (Lifecycle, then Approval Workflow). A future requester that called `transition(…, PENDING_APPROVAL)` directly would leave a request with no deadline. The expiry sweep skips such a request, so it would block the court until a manager decides. Today the only path is `submit_for_approval`.
- **The reason code reaches the API caller only as `detail` text.** `backend/CLAUDE.md` keeps the plain-string error shape until the frontend can parse codes.
- **Check-in has no time window.** It is outside the baseline (§9); adding one is a product decision, not a DD one.
- **The blocking-state set is still defined in several places (AD-2).** Not reopened here.

### Commit/tag

Implementation, tests and design: commit `5b2411e` (branch `feat/c05-detailed-design`). Merged to `main` in [PR #91](https://github.com/tylmarek1/C01/pull/91). Tag **`c05-detailed-design`** points to that merge commit.

### Follow-up 2026-10-19 — DD-T1 checks the code against BR-09, not against itself

- **Found:** DD-T1 claimed "`ALLOWED_TRANSITIONS` = BR-09", but its
  expected values were read from `ALLOWED_TRANSITIONS` itself, so it could
  not catch a difference. There was one: the code allowed
  `CONFIRMED → COMPLETED`, which BR-09 and the §5.2 statechart don't have
  (a slot without a check-in ends `NO_SHOW`; only `CHECKED_IN` completes).
  No code path used the edge; the DD's fulfilment row had copied it.
- **Which source was wrong:** the code (and the DD row copied from it). The
  specification was right and stays unchanged.
- **Change:** the edge is removed from `lifecycle.py`. `backend/tests/test_lifecycle.py`
  now has `BR_09_EDGES` and `BR_09_GUARDED_EDGES`, written down from the
  specification's BR-09 table. DD-T1 uses them as the oracle for all
  9 × 9 pairs and checks `ALLOWED_TRANSITIONS` and `GUARDS` against them.
- **Mutation check:** with the old `lifecycle.py` restored, the new DD-T1
  fails (2 failed: the `CONFIRMED → COMPLETED` pair and the table equality); the
  old DD-T1 had passed on that code. With the fix: 82 passed (`-k t1`).

## C06 Internal Evidence Assessment

**Assignment:** `docs/course/C06.md` (owner part, § 11) and `docs/course/C07-C08.md`
(part "Dnes: C06 assessment findings → ověřené rozhodnutí").
**Assessed by:** team HAH, assessment dated 2026-10-25. **Disposition:** 2026-11-02, owner Adam Vrána for the team.

**Assessed baseline:** tag `v4.1.0` = `4a23dc1` (main, clean tree). Every
finding below was reproduced against that baseline before anything was changed.
**Fix / reporting baseline:** tag `v4.1.1` (this change, PR "fix: close the
two C06 findings"). Links old → new are per finding.

HAH's checklist: B1–B2, R1–R5, A1–A4, D1–D3, D5 = YES; Q1–Q3 = N/A (no C04
assignment, accepted by HAH as N/A); **D4 = PARTLY** (cause: F1). Three
candidates: F1 and F2 verified, F3 rejected by HAH itself.

### Verified findings

**F1 — Approve confirms a mere `PENDING` hold on a normal court**

- **Claim:** OP-05 (Approve) acts only on a `PENDING_APPROVAL` request.
  `docs/specification.md` OP-05 precondition "state = PENDING_APPROVAL",
  REQ-08, VE-05.3 ("approve a PENDING hold … → CONFLICT, state unchanged").
- **Expected:** `POST /reservations/{id}/approve` on a `PENDING` hold → 409, state unchanged, no event, no notification.
- **Observed (HAH):** on a court without `requires_approval` → 200,
  `CONFIRMED`, a `CONFIRMED` event noted "Approved", a "Reservation approved"
  notification. On an approval court `_no_approval_needed` refused it by accident.
- **Verify (ours, on `v4.1.0`):** `test_ve_05_3_approve_from_any_other_state_is_a_conflict`
  parametrised over both court kinds, run with `v4.1.0`'s
  `backend/src/reservations/lifecycle.py`: **1 failed, 5 passed**. The failing
  case is `[False-PENDING]` (normal court, `PENDING`), exactly HAH's case.
  Root cause: `approve_reservation()` passes `approval_decision=True`. The Lifecycle
  checked that flag only on the edges out of `PENDING_APPROVAL`. The `PENDING → CONFIRMED`
  guards (hold alive, court active, no approval needed) all pass on a normal court.
- **Which source was wrong:** the code. The specification (OP-05, VE-05.3) and C03 G3 ("`PENDING → CONFIRMED`
  is requested only by Confirm on a normal court") were right and stay unchanged.
  The VE-05.3 test was too narrow: it used only an approval court, so it
  could not see the gap. HAH's D4 PARTLY says the same about the DD tests.
- **Disposition:** VERIFIED FINDING → **ACCEPTED — change required.**
- **Action:** `check_transition()` now refuses a manager decision on any reservation that is not
  `PENDING_APPROVAL`: `Rejection.NOT_AWAITING_APPROVAL`, 409, before any guard
  and before any write. It lives in the Lifecycle, not only in the route,
  because the Lifecycle owns "may this transition happen" (C03 R2). So no
  future caller that passes `approval_decision=True` can repeat this. DD amendment:
  `docs/architecture-and-decisions.md` § "C05 Detailed Design", *Amendment (2026-11-02)*.
- **Closure evidence:** VE-05.3 now runs on both court kinds (6 cases, all
  passing). DD-T4 has a unit case: a live hold → `CONFIRMED` passes without a decision and is
  `NOT_AWAITING_APPROVAL` with one. DD-T3 no longer passes a decision to
  Confirm, which the new rule correctly refused. Full suite: see "Verification run" below.

**F2 — the venue-local-time regression test was seasonal**

- **Claim:** BR-04 is checked in Europe/Prague (Known pitfall #1). Evidence claimed: "487 passed" (`docs/project-state.md`, 2026-10-19).
- **Expected:** the regression test checks the rule in any season, and the claimed evidence can be reproduced on the baseline.
- **Observed (HAH, 2026-10-25):** 486 passed, 1 failed:
  `test_create_reservation_uses_venue_local_time_not_utc` sends a fixed
  `05:00Z` and assumes it is 07:00 local (CEST). After the clocks change on
  2026-10-25, today + 3 days is in CET, `05:00Z` is 06:00 local, and the
  app correctly returns 422.
- **Verify (ours, on `v4.1.0`):** the `v4.1.0` test run on 2026-11-02 →
  `assert 422 == 201`. The same test with the clock moved to 2027-06-15
  (`uv run --with time-machine`, test process only) → passes. So the
  product follows BR-04 and the oracle depends on the season.
- **Which source was wrong:** the test, which was the verification evidence. The product and the spec were right.
- **Disposition:** VERIFIED FINDING → **ACCEPTED — change required.**
- **Action:** the test now builds the UTC instants from local 07:00 and 06:00
  Europe/Prague on the day under test. It asserts that 07:00 local, the
  opening, is 201 and 06:00 local is 422. The boundary is now checked from both sides.
  Before, only the accepted side was checked.
- **Closure evidence:** the new test passes with the clock at 2026-11-02
  (CET), 2027-03-26 (the day before CEST starts, so the booked day is in CEST)
  and 2027-06-15 (CEST). Each was run with `time-machine` travel, 1 passed each.

### Rejected candidate

**F3** — an approval request without a deadline. Rejected by HAH itself:
`approval_service.submit_for_approval()` is the only caller of
`transition(…, PENDING_APPROVAL)`, and it sets `approval_expires_at` in the
same transaction. **Owner disposition: ACCEPTED — no immediate change.** We agree with
the rejection. The risk applies to future code only and is already listed in § "C05 DD
Verification Evidence" → "Remaining design risk".

### Owner disposition

| Finding | Disposition | Reason / evidence | Action / no-change | Owner | Status |
|---|---|---|---|---|---|
| F1 | ACCEPTED — change required | reproduced on `v4.1.0`: VE-05.3 `[False-PENDING]` 200 ≠ 409 | Lifecycle refuses a decision outside `PENDING_APPROVAL`; VE-05.3 on both court kinds; DD-T4 case; DD amendment | Adam Vrána | closed in `v4.1.1` |
| F2 | ACCEPTED — change required | reproduced on `v4.1.0`: `422 == 201` in CET, passes in CEST | test derives UTC from local time and checks both sides of the opening | Adam Vrána | closed in `v4.1.1` |
| F3 | ACCEPTED — no immediate change (rejected candidate) | single caller sets the deadline (HAH's own check) | none. The risk stays recorded under C05 "Remaining design risk" | — | no change |

### Actions / justified no-change decisions

- F1, F2: fixed (above). The spec, C03 architecture and C05 DD intent are unchanged. The DD
  gets one amendment that records the new refusal reason.
- `docs/project-state.md` "Latest verification" no longer gives a test count
  without a date and tag. A count is true only for the commit and the day it
  was run, which is what F2 showed.

### Remaining evidence gaps

- The suite still depends on the real clock (`datetime.now()` plus a few
  days). F2's test is now season-proof. The other tests were not run with
  a moved clock in this change, so they are **NOT VERIFIED** beyond the
  dates they actually ran on. Tracked as R-03 in § "Risk Assessment" below.
- The Lifecycle's lock precondition (callers hold `FOR UPDATE`) is still a
  documented contract, not a mechanical check. DD-T9 checks only one race. Tracked as R-04.

### Verification run

`cd backend && uv run pytest -q` on the fix, 2026-11-02, PostgreSQL 16: **490 passed** (4.1.0 had 487; +3 = VE-05.3 on a normal court).

## Risk Assessment

**Assignment:** `docs/course/C07-C08.md` part B. **Date:** 2026-11-02. **Reporting baseline:** `v4.1.1`.
Classification per B3/B4: L × I, 1–2 LOW, 3–4 MEDIUM, 6–9 HIGH. An actual
residual is given only where the treatment has been carried out and its
effect checked. Otherwise it is NOT VERIFIED.

The two C06 findings are **issues/defects, not risks** (they had already happened). Both are closed in `v4.1.1`, see above.
Open issue: **planning gap**, there is no committed CP2 date or scope in
`docs/course/` yet, so slide 03 of the status report has no CP2 plan date.
Owner: team (Adam Vrána), resolved once CP2 is announced.

| | R-01 | R-02 | R-03 | R-04 | R-05 | R-06 |
|---|---|---|---|---|---|---|
| **Category** | People / Resources | Release / Operation | Technical / Quality | Technical / Quality | Scope / Requirements | External dependency |
| **Cause → event → consequence** | Most of the code and docs come from one member (`git shortlog -sn`: 126 of 146 commits by one author) → in the CP1 defence another member can't explain or run a part → the "Engineering Review & Defence" score drops; if that member is away, nobody can change the system | No CI. The 8-minute suite runs only when someone remembers → a regression or a date-dependent failure sits on the tag that is reported as verified → a "Verified" claim is false at the defence (it already happened once: F2) | Tests build dates from the real clock (today + N days, DST, the 14-day booking window) → another test turns red on some future date with no code change → false red, or a red the team learns to ignore | `transition()` needs the caller to hold the row lock, but nothing checks it → a new call site without `FOR UPDATE` lets two transitions on one reservation both succeed → state/audit inconsistency. BR-02 double booking stays impossible, because the DB constraint enforces it | Operation preconditions (OP-0x "Preconditions") are partly enforced by guards that only happen to cover them (F1 was one) → another spec ↔ code gap is found at CP1/CP2 → rework, a lower "Working Solution & Evidence" score | Web Push needs browser push services and VAPID keys → push does not arrive during the demo (network, permission, browser) → the H1 notification step looks broken |
| **Initial L / I → priority** | L=2 (the commit share is a fact; the defence is in a week), I=3 (graded defence of the whole team) → **HIGH (6)** | L=2 (happened once already), I=3 (CP1 "Working Solution & Evidence") → **HIGH (6)** | L=2 (one such test was found), I=2 (fixable, but it costs a release) → **MEDIUM (4)** | L=1 (every current call site locks; it would take new code), I=3 (state invariant) → **MEDIUM (3)** | L=2 (F1 shows the pattern exists), I=2 → **MEDIUM (4)** | L=2, I=1 (the in-app inbox, R7, shows the same notification with no push) → **LOW (2)** |
| **Strategy** | MITIGATE | MITIGATE (+ decision on CI) | MITIGATE | ACCEPT (with monitoring) | MITIGATE | ACCEPT (with contingency) |
| **Treatment & owner / due** | Every member does a clean checkout + `uv run pytest` per README on their own machine, and presents one of the A steps (A1–A5) at a dry run. Owners: Marek Tyl, Josef Glogar, Adam Mikoláš; due 2026-11-09 | Full suite on the reporting tag on defence day, output saved. The team decides whether to add a GitHub Actions job (Postgres service + pytest) before CP2. Owner: Adam Vrána; due 2026-11-09 | F2 fixed and checked in 3 seasons (done). Run the whole suite once with the clock moved (summer, the eve of a DST change). Owner: Adam Vrána; due 2026-11-09 | Review rule: every new `transition(` call site in a diff must show its lock. DD-T9 keeps the race test. Acceptance owner: Adam Vrána | Go through OP-01…OP-06 preconditions against code + VE tests, on both court kinds wherever the court kind changes the path. Owner: Marek Tyl; due 2026-11-09 | Demo uses the in-app notification inbox; push is shown only if it works on the demo machine. Acceptance owner: Adam Vrána |
| **Treatment evidence** | none yet | `v4.1.1` suite run 2026-11-02 (`docs/project-state.md`); the CI decision is open | F2 closure above (3 × 1 passed); the full-suite clock run not done yet | `lifecycle.py` docstring (contract), DD-T9 | F1 closure (OP-05 done); OP-01…04, OP-06 not yet swept | in-app inbox: `notifications.py`, existing tests |
| **Expected residual** | L=1, I=2 → LOW (2) | L=1, I=2 → LOW (2) with CI; L=1, I=3 → MEDIUM (3) without | L=1, I=2 → LOW (2) | L=1, I=3 → MEDIUM (3) (unchanged, accepted) | L=1, I=2 → LOW (2) | L=2, I=1 → LOW (2) |
| **Actual residual** | NOT VERIFIED | NOT VERIFIED (one run is not a control) | NOT VERIFIED (only F2's test is proven season-proof) | MEDIUM (3), accepted | NOT VERIFIED | LOW (2), accepted |
| **Acceptance & contingency** | Adam Vrána accepts after the dry run. If a member can't run it, pair with them before the defence | Adam Vrána. If the defence-day run is red, report it as an open issue in the status report, not as Verified | Adam Vrána. A red date-dependent test is fixed like F2 (derive from local time), never skipped | Adam Vrána; contingency: DB constraint still guarantees BR-02 | Adam Vrána; a gap found is fixed or listed as an open issue | Adam Vrána; contingency: show the outbox row and the delivery state instead |
| **Monitoring / trigger** | Trigger: a member can't run the suite or answer a walkthrough question | Trigger: any merge to `main` without a recorded suite run; the defence-day run is red | Trigger: a failing test whose diff is empty; a DST change date in the window (2027-03-28) | Trigger: a diff adds a `transition(` call site or changes `_get_owned_reservation` | Trigger: a VE test that runs on one court kind only, for an operation whose path depends on it | Trigger: push delivery state `FAILED` in the dry run |

### Follow-up 2026-11-02 — risk treatments carried out (reporting baseline `v4.1.2`)

Treatments that could be done without the other team members, run the same day.
Initial ratings stay as recorded above. Only the residuals change, and only where there is evidence.

**R-05: precondition sweep (OP-01…OP-06), done.** Each `docs/specification.md` "Preconditions" clause was mapped to where the code enforces it and to its VE test:

| Operation | Clause → enforcement → test | Court-kind dependent? | Gap found |
|---|---|---|---|
| OP-01 Create | auth (`get_current_user`, VE-01.4); court exists/active (`_get_court_or_404`, VE-01.3); interval/shape (schema, VE-01.2/01.2b/01.5); window (`check_within_booking_window`, VE-01.6); hours (`check_within_opening_hours`, VE-01.11/01.12); facility block (`check_facility_available`, VE-02.5); limits (`check_active_reservation_limit`, VE-01.8/01.10) | no | none |
| OP-02 Availability | court active, interval shape (VE-02.6, VE-02.8) | no | none |
| OP-03 Confirm | `state = PENDING`, hold alive, court active (Lifecycle edge + `GUARDS`, VE-03.2/03.3/03.4); owner or manager (`_get_owned_reservation`, VE-03.5) | **yes**: a normal court goes `PENDING → CONFIRMED`, an approval court goes `PENDING → PENDING_APPROVAL` with its own guard row | VE-03.2/03.3/03.4 ran only on a normal court |
| OP-04 Cancel | state set + `now < start` (`check_cancellable`, VE-04.3/04.4/04.5, DD-T5); owner or manager (VE-04.6) | no, the same check on both | none |
| OP-05 Approve | `state = PENDING_APPROVAL` (F1 fix, VE-05.3 both kinds); deadline (VE-05.4); court active (VE-05.4b); venue manager (VE-05.2/05.9/05.10) | yes | closed by F1 |
| OP-06 Reject | `state = PENDING_APPROVAL` (edge table, VE-06.3); deadline (VE-06.4); venue manager (VE-06.2/06.6) | yes, a different path on a normal court | VE-06.3 ran only on an approval court |

Action: VE-03.2, VE-03.3, VE-03.4 and VE-06.3 are now parametrised over both court
kinds. Result: **16 passed**. All four preconditions already held on the
other court kind, so **no new defect**: only the evidence was incomplete.

**R-02: CI added, done.** `.github/workflows/ci.yml` runs the backend suite
against a PostgreSQL 16 service, plus the frontend `npm ci && npm run build && npm run lint`, on
every PR, push to `main` and `v*` tag. First run, PR #96
(GitHub Actions run 41367706826): **backend success, frontend success**. The
runner's clock is in UTC, not Europe/Prague, so CI also checks the suite
under a different local offset (pitfall #1).

**R-03: full suite with a moved clock, partly done.** `uv run --with
time-machine` with the clock at 2027-06-15 (CEST, test process only):
**495 passed, 3 failed**: `test_admin_stats_window_days_changes_the_recent_count`,
`test_reviews_written_metric`, `test_trending_courts_ranks_by_recent_bookings`.
All three compare `created_at` with a "last N days" window. `created_at` is
set by PostgreSQL (`server_default=func.now()`, the real 2026 clock), and
the window comes from Python's `datetime.now()`, which was moved to 2027. So
the failures come from the method: only one of the two clocks was moved.
They are not seasonal defects. All three pass on the real clock (490 passed today) and in CI. Every
booking-rule test (windows, opening hours, holds, deadlines) passed under the summer clock.
Remaining gap: those three "recent window" tests can't be checked with this
method. They would need the DB clock moved too.

| Risk | Treatment status | Actual residual |
|---|---|---|
| R-01 People | not done. It needs each member's own clean run and dry run | **NOT VERIFIED** (still HIGH 6 until done) |
| R-02 Release | CI added and green on its first run | **L=1, I=2 → LOW (2)**: one green run is evidence that the control works. Re-check on every red run |
| R-03 Tech/time | suite under a summer clock: 495/498, the 3 others explained above | **L=1, I=2 → LOW (2)** for the booking rules; the 3 "recent window" tests NOT VERIFIED by this method |
| R-04 Tech/locks | accepted | MEDIUM (3), unchanged |
| R-05 Scope | sweep done, 4 tests widened, no new defect | **L=1, I=2 → LOW (2)** |
| R-06 External | accepted | LOW (2), unchanged |

The decision requested in the first draft of the status report ("add CI before
CP2?") was taken: **yes, added** (Adam Vrána for the team, 2026-11-02).

**Schedule correction (2026-11-02):** the CP1 defence (A + C) is on the
exercise right after C07, not a week later. So R-01's treatment (each member's own clean run + dry run)
cannot finish before the defence. It moves to **2026-11-16** (owner Marek
Tyl) and stays **NOT VERIFIED, HIGH (6)** at the defence. The status
report says so and stays AMBER. A step of part A that its speaker hasn't
verified is presented by Adam Vrána. The other treatments and residuals above are unchanged.
