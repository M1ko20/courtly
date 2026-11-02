# Courtly — Sports Court Reservations

A reservation system for sports venues: players book tennis, volleyball
and badminton courts online, a venue never double-books a court, and
both sides always see the same, accurate schedule.

<p align="center">
  <img src="docs/screenshots/landing.png" alt="Courtly landing page" width="49%" />
  <img src="docs/screenshots/booking.png" alt="Courtly booking: the schedule board with a picked slot and the court pass" width="49%" />
</p>

- **Repository:** https://github.com/tylmarek1/C01
- **Run it locally:** see [Run](#run) below.

## What it does

Players sign up, browse courts by sport and amenity, check live
availability, and book a slot in seconds — no phone calls, no shared
spreadsheets. A new booking is held for 5 minutes while the player
confirms it; on courts a venue manager has marked as requiring approval,
confirming submits a request instead, which the manager approves or
rejects. The database itself — not application code — guarantees two
players can never end up holding the same slot, even under heavy
concurrent demand (see [Architecture & decisions](#architecture--decisions)).

### For players

- Browse, search and filter courts by sport and amenity; check live
  occupancy and reviews before booking.
- Book a 60/90/120-minute slot, with a 5-minute hold before confirming
  (or an approval step on courts that require it).
- See the price of a slot before booking (the venue's rates by weekday and
  time of day), and pay online or in cash at the desk. Online payments go
  through a test gateway for now. A released booking is refunded.
- Recurring weekly bookings, rescheduling, and cancellation any time
  before the slot starts.
- A waitlist that automatically offers a slot to the next person in line
  when it frees up.
- Social features: invite guests, open a booking to other players and
  accept join requests, split the cost with everyone attending.
- Favorites, reviews (with photos and comments), achievements, seasonal
  challenges, skill ratings and a leaderboard, and personal stats.
- A public player profile with a follow feature, real-time chat (direct
  messages, plus a group chat for each reservation and each persistent
  team/club you're in), and an activity feed of what players you follow
  are up to.
- A personal calendar feed (Google/Apple/Outlook) and in-app
  notifications, including browser push.
- A built-in Help Center (getting-started guide, a plain-language
  reservation-status glossary, FAQ), a full English/Czech UI, and a
  light/dark theme.

### For venue managers

A venue manager runs only the venues they're assigned to: they see and
act on only those venues' courts, reservations and payments.

- Manage the venue: details and weekly opening hours.
- Manage courts: create/edit, set rates by weekday and time of day and
  amenities, upload a photo, and flag a court as requiring approval.
- An approval queue for requests on approval-required courts.
- Payments: record a cash payment, confirm handing cash back for a released
  booking, retry a refund the gateway refused.
- Block a court for maintenance — any booking that overlaps the window is
  cancelled automatically.
- Oversee their venues' reservations: confirm, cancel, check in, view a
  reservation's history, export them to CSV.
- An analytics dashboard: status breakdown, busiest hours, top courts,
  per-court utilization, no-show rate.
- Run a seasonal challenge (e.g. "play 10 sessions this autumn") for
  players to complete.
- Promote a player to venue manager, or demote a manager of their own
  venues.

### For admins

Everything a venue manager can do, plus:

- Grant or revoke anyone's role, including another admin's.
- Create venues and assign their managers.
- Read the audit log of who changed what.
- Permanently delete a court that has no reservation history (deactivate
  is still the tool for retiring a court that's actually been used).

## Domain at a glance

| Concept | In this system |
|---|---|
| **Resource** | `Court`: sport type (TENNIS / VOLLEYBALL / BADMINTON), indoor/outdoor, active flag; each court belongs to a `Venue` |
| **Reservation** | one court, one user, one time slot `[start_time, end_time)`, timestamptz |
| **User** | `Player` (books/confirms/cancels own reservations), `Venue manager` (manages the courts of their own venues and acts on those venues' reservations), or `Admin` (everything a venue manager can, plus role management and permanently deleting a court) |
| **States** | `PENDING` (a 5-minute hold) `→ CONFIRMED`; on courts that require approval `PENDING → PENDING_APPROVAL → CONFIRMED / REJECTED`; `→ CANCELLED` before the start; unanswered holds/requests `→ EXPIRED`; then `CHECKED_IN → COMPLETED / NO_SHOW`. Full lifecycle: [`docs/specification.md`](docs/specification.md) |
| **Operations** | create · check availability · confirm · cancel · approve/reject (approval-required courts) |
| **Common rule** | two reservations that hold a court (`PENDING`, `PENDING_APPROVAL`, `CONFIRMED`, `CHECKED_IN`) must never overlap |
| **Domain-specific rule** | a reservation must be 60/90/120 minutes, start on `:00`/`:30`, and lie fully within the venue's opening hours (07:00–22:00 unless a manager changes them) |
| **External boundary** | Notification Service — currently implemented as in-app notifications; e-mail delivery was the original plan and is not yet built |

Full rationale, assumptions, open unknowns and the domain's selected
future pressure are in [`docs/intent-and-change.md`](docs/intent-and-change.md).

## Architecture & decisions

**Backend:** Python 3.12 · FastAPI · SQLAlchemy 2 · psycopg 3 · PostgreSQL 16 ·
pytest · [uv](https://docs.astral.sh/uv/) · Docker Compose
**Frontend:** React 19 · TypeScript · Vite · Tailwind CSS 4 · shadcn/ui
components · React Router · TanStack Query

Python/FastAPI was picked for team familiarity; PostgreSQL because its
exclusion constraints let the database itself guarantee the no-overlap
rule under concurrency, instead of relying on application-level locking
(ADR-000/ADR-001). The repository is split into [`backend/`](backend/) and
[`frontend/`](frontend/) (ADR-002) so each half's own toolchain — `uv` vs
`npm` — stays unambiguous, and auth is stateless JWT rather than
server-side sessions (ADR-003). Full rationale and every other decision:
[`docs/architecture-and-decisions.md`](docs/architecture-and-decisions.md).

Schema changes go through Alembic migrations (ADR-006,
`uv run alembic upgrade head`). There is no CI pipeline yet — a known,
deliberate gap rather than an oversight.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (installs Python 3.12 automatically)
- Node.js 20+ and npm (for the frontend)
- Docker with Compose (for PostgreSQL)

## Run

```bash
docker compose up -d --wait db   # start PostgreSQL on localhost:5432 (from the repo root)

cd backend
cp .env.example .env             # optional: falls back to the same defaults
uv sync                          # create .venv and install dependencies
uv run pytest -v                 # run tests against the real database
uv run python -m reservations.seed        # insert a few demo courts
uv run fastapi dev src/reservations/main.py &   # API at http://localhost:8000 (docs: /docs)
curl localhost:8000/health       # -> {"status":"ok"}

cd ../frontend
npm install
npm run dev                      # app at http://localhost:5173
```

Stop the database with `docker compose down` (add `-v` to wipe its data). See
[`backend/README.md`](backend/README.md) and [`frontend/README.md`](frontend/README.md)
for configuration details, the full API reference and the frontend's design
system (documented in [`DESIGN.md`](DESIGN.md)).

## Repository layout

```
backend/                            FastAPI application (see backend/README.md)
frontend/                           React application (see frontend/README.md)
docker-compose.yml                  shared PostgreSQL instance for both apps
docs/                                specification, architecture decisions, domain
                                     frame, project status, and the course-work
                                     history this project grew out of (see below)
docs/screenshots/                   README preview images
DESIGN.md                           the UI design system — tokens, components, patterns
```

## Learn more

This README covers the project as it stands today; the fuller history —
original course assignments, specification revisions, decision records,
and executed evidence — lives in [`docs/`](docs/) rather than here:

- [`docs/specification.md`](docs/specification.md) — the full behavioral
  specification: every operation, business rule, state and edge case.
- [`docs/architecture-and-decisions.md`](docs/architecture-and-decisions.md)
  — the architecture decision records (ADR-000…010), the C03 architecture
  (Confirm Reservation and the notification boundary) and the C05
  detailed design (the reservation lifecycle).
- [`docs/intent-and-change.md`](docs/intent-and-change.md) — the original
  domain frame (actors, concepts, rules).
- [`docs/project-state.md`](docs/project-state.md) — where the course work
  stands right now: each exercise's status and where its evidence lives.
- [`docs/evidence-and-evolution.md`](docs/evidence-and-evolution.md) — what
  was actually run and observed for each exercise, dated.
- [`docs/course/`](docs/course/) — the original course assignments,
  verbatim.

### Course work at a glance

| Exercise | Artifacts | Tests / evidence | Tag / commit |
|---|---|---|---|
| C01 | `docs/intent-and-change.md` (Project Frame) | `docs/evidence-and-evolution.md` § "C01 Engineering Spike" | PR #5 |
| C02 | `docs/specification-v0.1.md` (baseline), `docs/specification-v0.2.md` (approval change), `docs/change-c02-impact.md`; current `docs/specification.md` (v0.3) | `backend/tests/test_spec_baseline.py` (VE-01…04), `backend/tests/test_approval_api.py` (VE-05…08) — each test name starts with its VE id; § "Evidence C02" | commit `ede421d` (PR #9) |
| C03 | `docs/architecture-and-decisions.md` § "C03 Part A" and § "C03 — Architecture" (ADR-005) | `backend/tests/test_architecture.py`; § "C03 — Architecture Evidence" | `c03-architecture` |
| C04 | none — the course had no C04 assignment (C03 took its place; the slot was the CP1 checkpoint, `docs/course/C02.md` "Vztah k CP1") | — | — |
| C05 | `docs/architecture-and-decisions.md` § "C05 Detailed Design" (unit: `backend/src/reservations/lifecycle.py`) | `backend/tests/test_lifecycle.py` (DD-T1…T9); § "C05 DD Verification Evidence" | `c05-detailed-design` |
| C06 | assessment of our `v4.1.0` by team HAH; owner disposition in `docs/evidence-and-evolution.md` § "C06 Internal Evidence Assessment" | F1/F2 reproduced on `v4.1.0`, closed by VE-05.3 (both court kinds), DD-T4, and the season-proof BR-04 test | assessed `v4.1.0`, fixed `v4.1.1` |
| C07–C08 | `docs/evidence-and-evolution.md` § "Risk Assessment" (part B); status report and design review are presented from tag `v4.1.1` | see the C06 row | `v4.1.1` |

The latest release tag (see `CHANGELOG.md`) marks one baseline of docs,
code and tests together. Status of each exercise: `docs/project-state.md`.

## Team

Courtly started as the **SWI** course's engineering-spike deliverable and
was then expanded by the team into a fuller product. Team **VTG Courts**:
Adam Vrána, Marek Tyl, Josef Glogar, Adam Mikoláš. Development happens on
feature branches merged into `main` via reviewed pull requests.
