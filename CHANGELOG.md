# Changelog

All notable user- or developer-visible changes to Courtly (C01) are
documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Changes accumulate under `Unreleased` and move under a dated version heading
when the team cuts a release; each release has a git tag of the same name
(`v4.1.0`, …).

## [Unreleased]

## [4.1.2] - 2026-11-02

Tests, CI and docs only: backend stays 0.4.1, frontend stays 4.1.0. This
is the C07–C08 reporting baseline.

### Added

- **CI:** GitHub Actions runs the backend suite on PostgreSQL 16 and the frontend build and lint on every PR, push to `main` and release tag.

### Changed

- **Precondition tests on both court kinds:** the Confirm precondition tests (VE-03.2, 03.3, 03.4) and the Reject one (VE-06.3) now run on both court kinds.
- **Docs:** the risk-treatment results are recorded in `docs/evidence-and-evolution.md`.

## [4.1.1] - 2026-11-02

Backend-only patch: backend 0.4.0 -> 0.4.1, frontend stays 4.1.0. Closes
the two verified findings of the C06 assessment of `v4.1.0`.

### Fixed

- **Approve on an ordinary hold:** a venue manager's Approve on a `PENDING`
  hold of a court without approval no longer confirms it as "approved". It
  returns 409 "This reservation is not awaiting approval", as OP-05/VE-05.3
  specify. The Lifecycle refuses a manager decision on anything that is not
  `PENDING_APPROVAL` (`Rejection.NOT_AWAITING_APPROVAL`).
- **Season-dependent test:** the venue-local-time regression test for
  opening hours assumed summer time and failed after the clocks changed.
  It now derives the UTC instants from Europe/Prague local time and checks
  both 06:00 (rejected) and 07:00 (accepted).

### Documentation

- Course assignments C06 and C07–C08 added under `docs/course/`. The C06 owner
  disposition and the C07–C08 risk register are in `docs/evidence-and-evolution.md`,
  and the DD has an amendment for the new refusal reason.

## [4.1.0] - 2026-10-19

Backend 0.3.2 -> 0.4.0, frontend 4.0.0 -> 4.1.0. Everything merged since
4.0.2: venues and venue-scoped managers (specification v0.3), opening hours
and court rates in the database, payments, the audit log, Alembic
migrations, and the C05 detailed design of the reservation lifecycle.

### Added

- **Prices and payments for players:**
  - **Booking page:** quotes the picked slot from the court's rates.
  - **Closed days:** a closed day says so on the booking page, the court page and the reschedule dialog.
  - **Reservation cards:** show the booked price, the payment status, and a "Pay" action. The payment dialog is honest about the test gateway and can simulate a declined card.
  - **Reservation detail:** shows the payment history.
  - **"Open now" strip:** follows the venue's real hours for today (or counts open venues when there are several).
- **Venue desk UI for venues, pricing, payments and the audit log:**
  - **Venues tab:** venue details, a weekly opening-hours editor, and manager assignment (admins).
  - **Courts tab:** a rate editor per court (the same rate on several weekdays in one row), and venue selection for a new court. A venue manager sees only their own venues' courts.
  - **Payments tab:** filter by status, hand back cash, retry a failed refund.
  - **Reservations tab:** payment status badge and "record cash payment".
  - **Audit log tab (admins only):** readable values.
  - The utilization heatmap follows the venue's real opening hours.
  - Saving unchanged opening hours or rates no longer fills the audit log; the backend now updates rows in place.
- **Payments, completed:** cash of a released reservation is handed back at
  the desk and confirmed by a manager; the payer is notified when a payment is
  received or refunded; a refund the gateway keeps refusing alerts the venue's
  managers and admins and can be retried; `GET /payments` lists a venue's
  payments; reservation lists show each one's payment status.
- **Payments** (ADR-010), through a mock gateway until a provider is chosen:
  the booker pays a reservation's quoted price
  (`POST /reservations/{id}/payments`, `decline: true` simulates a refusal);
  a venue manager records cash; cancelling, rejecting or expiring a paid
  reservation queues a refund that the background worker makes. Paying
  doesn't change a reservation's state.
- **Opening hours and court rates in the database** (ADR-009, specification
  v0.3 BR-04): opening hours per venue and weekday (a day can be closed) instead of
  a fixed 07:00–22:00; court rates by weekday and time on top of the base
  `price_per_hour`; `GET /courts/{id}/quote`; every reservation keeps the price
  quoted when it was booked (`price_total`), which the cost split now uses.
  Existing venues keep 07:00–22:00 daily.
- **Venues and venue-scoped managers** (ADR-008, specification v0.3): courts
  belong to a venue; admins create venues and assign managers
  (`/venues`, `/venues/{id}/managers/{user_id}`); a venue manager can only
  manage, approve, block, reply and report for their own venues. Existing
  courts and managers are migrated into one venue, so nothing changes for
  them. `POST /courts` takes an optional `venue_id`.
- **Structured logs and an audit log** (ADR-007): every response carries an
  `X-Request-ID`; every `reservations.*` log line carries the request id and
  user id (`LOG_FORMAT=text|json`), with one access line per request. Changes to
  courts, users (name/email/role), reservations (time/status) and facility
  blocks are recorded in `audit_log` in the same transaction; admins read it
  at `GET /admin/audit-log`.
- **Alembic migrations** (ADR-006): the schema is built by
  `uv run alembic upgrade head` (the seed and the tests do it too) instead of
  `create_all`. An existing dev database is adopted by stamping the `0001`
  baseline — no data is touched. `tests/test_migrations.py` fails on
  model↔migration drift, a missing enum value, or a broken downgrade.
- **Click a time straight on the day's timeline** (booking page, court
  detail, reschedule dialog): hovering previews the nearest free slot for the
  chosen duration, a click selects it, a click on a taken stretch offers the
  waitlist, and the chosen range stays drawn on the strip with its times.
  The booking step header shows the picked time too.


- **Demo-account picker on the login page (dev builds only):** clicking a
  seeded account (player, teammate, venue manager, admin) fills in the form.
  Production builds don't ship the credentials.
- **Plural forms in translations:** `t()` understands an ICU-style
  `{count, plural, one {…} few {…} other {…}}` subset backed by
  `Intl.PluralRules`, so Czech counts decline correctly ("2 místa", "5 míst").

### Changed

- **Rescheduling uses the same day strip and free-time grid as booking**
  instead of bare date/time inputs, so only actually free times can be picked.


- **Czech copy reviewed page by page:** literal translations reworded into
  natural Czech, check-in no longer translated as "přihlásit se" (it clashed
  with login; now "potvrdit příchod" / "Na místě"), one term each for the
  waitlist ("pořadník"), no-shows ("neúčast") and skill rating.
- The public navbar's language and theme switches now sit at the far right.
- **Reservation lifecycle (C05 detailed design):** every BR-09 guard is now
  checked by the Lifecycle itself, as an ordered guard table with a reason
  code per refusal (`TransitionRejected`, still a 409 with the same message).
  Two guards that only the callers used to ensure are new: a hold or
  approval request can be expired only after its deadline, and only a court
  that requires approval accepts a submission. The decision instant can be
  injected, so the policy is unit-tested without a database.

### Fixed

- **Check-in racing a cancel:** both could succeed, leaving a `CHECKED_IN`
  reservation with a `CANCELLED` event in its history. Check-in now takes the
  reservation's row lock like every other state change, so exactly one wins.
- The help FAQ named a "Private profile" switch that doesn't exist; it now
  points at the real "Show my profile to other players" setting.

- **Reservation lifecycle matches the specification's transition table:**
  it no longer accepts `CONFIRMED → COMPLETED` (BR-09 has no such edge; a
  slot that ended without a check-in is a no-show). No code path used it.
  The lifecycle unit tests now take the expected transitions from the
  specification instead of from the code.

## [4.0.2] - 2026-10-08

Backend-only patch: backend 0.3.1 -> 0.3.2, frontend stays 4.0.0.

### Fixed

- **Accepting a waitlist offer now respects the same per-player limits as
  booking:** the active-reservation limit and the no-show booking pause.
  Before, a player already at the limit, or paused for no-shows, could get
  another booking through the waitlist. A refused accept leaves the offer
  open. The player sees the reason (the same message as when booking) and
  can free a slot and accept again before the offer runs out.

## [4.0.1] - 2026-10-08

A backend-only patch release. The backend moves 0.3.0 -> 0.3.1 and the
frontend stays at 4.0.0. Separately, the C03 architecture milestone is
now tagged `c03-architecture` (PR #71's merge commit `da3158d`).

### Changed

- **Backend tests no longer wipe the dev database.** `uv run pytest` now
  runs in its own database (`reservations_test` by default, created on
  first run; override with `TEST_DATABASE_URL`). The seeded demo data stays
  in place, and the tests can run while the dev server is up. The fixture
  refuses to drop the schema of any database whose name doesn't end in
  `_test`.

### Fixed

- **Accepting a waitlist offer now goes through the reservation lifecycle**
  instead of creating the booking directly as confirmed. The booking gets
  the same guards and audit trail as a normal Book + Confirm. The one
  visible change: an offer on a court that was deactivated in the meantime
  is now refused (409) instead of being booked. A new architecture test
  (`backend/tests/test_architecture.py`) keeps every reservation status
  change inside `lifecycle.py`. This closes the open C03 risk "waitlist
  accept bypasses the Lifecycle" (AD-4).

## [4.0.0] - 2026-10-08

Version 4.0 is the product release of the "Clubhouse programme" redesign.
The jump from 0.3.0 to 4.0.0 was requested by the project owner to mark
the redesign as a closed milestone, not derived from semantic-versioning
rules. Only the frontend changed: `frontend/package.json` moves 0.2.0 ->
4.0.0, while the backend stays at 0.3.0 (no backend changes since v0.3.0;
the two deployables are versioned independently).

### Changed

- **New visual identity — "Clubhouse programme" — replacing the v0.3.0
  "court-side precision" look**, which read as a generic AI-generated SaaS
  dashboard. The direction combines six styles from the Refero library
  (Kikin, Monocle, Strava, Ballpark, Twitch "Stadium", Champions4good) into a
  sports club's printed match-day programme: warm paper, forest ink, one
  clay-court accent, Big Shoulders Display / Schibsted Grotesk / IBM Plex
  Mono, hairline rules instead of cards, 2–8px corners and no resting
  shadows. Tokens, fonts, favicon and every primitive (`button`, `badge`,
  `card`, fields, `tabs`, `dialog`, `switch`, `avatar`, toasts…) were
  rebuilt; `DESIGN.md` documents the new system.
- **The app shell is a masthead instead of a sidebar.** On desktop a forest
  venue strip (today's date, whether the venue is open right now in venue
  time, language, theme) sits above a sticky masthead with the section
  links, search, notifications, the "Book a court" action and the account
  menu. On mobile a top bar plus a bottom tab bar (Overview · Courts ·
  Book · Games · More) replaces the slide-out sidebar; "More" opens a
  numbered contents-style menu. Venue staff reach the admin panel through a
  single "Venue desk" link with the approval count.
- **Booking was redesigned around clarity.** Numbered steps whose numeral
  turns clay when done; a fixture-list day strip; the slot picker is now a
  ruled schedule board grouped by part of day, with the picked slot in clay
  showing its end time, taken/held/closed slots hatched *and* labelled,
  per-group free counts and a legend; the summary is a forest "court pass"
  with a tear-off perforation, sticky on desktop and a pass stub above the
  tab bar on mobile. The hold dialog stamps the slot "HELD" and shows the
  countdown as a large figure. "Repeat weekly" is now available on mobile
  too (it was desktop-only).
- Reservations render as **tickets** (sport-coloured date stub,
  perforation, one primary action + menu); the dashboard's next-up card is
  a forest match card; KPI tiles became scoreboard figures; courts are drawn
  as **painted court plans** in their real surface colours (tennis clay,
  volleyball blue, badminton green), and a new `SportTile` carries the same
  colours wherever a sport icon appears.
- The landing page was recomposed as a club poster (schedule-board hero
  with a stamped sticker, a sports ticker band, painted sport tiles,
  numbered steps, a contents-style feature index, a season-pass pricing
  ticket); auth screens, navbar, footer (with the giant wordmark), FAQ and
  CTA band follow the same system.

### Fixed

- The chat page's height now accounts for the shell chrome, so the
  composer is never pushed below the fold or under the mobile tab bar.
- After a slot was held, the picker no longer kept showing it as "your
  pick" while also marking it taken.

## [0.3.0] - 2026-10-07

### Added

- **Venue managers and admins now get a "Your venue at a glance" snapshot
  on their `/app` dashboard** instead of landing on the same empty
  player-style "book your first court" view every role saw before. Shown
  only for `VENUE_MANAGER`/`ADMIN` (`DashboardPage.tsx`), it surfaces
  pending-approval count, recent reservation volume, court count, and
  no-show rate (reusing the existing `GET /admin/stats` endpoint — no
  backend change), plus a direct link into the admin panel and, when
  approvals are waiting, a one-click deep link to the pre-filtered
  Reservations tab (`/app/admin?tab=reservations&status=PENDING_APPROVAL`,
  the same convention the notification bell already used). The player's
  own dashboard is unchanged.

- **The navbar itself now reflects which of the three roles is signed
  in**, not just which links are visible. The account dropdown header
  (`navbar.tsx`) shows a role badge (Player/Venue manager/Admin, reusing
  `ROLE_VARIANT`/`useRoleLabels` from `lib/user-role.ts`, the same pattern
  `AdminPage.tsx`'s user list already used) next to the name. For
  `VENUE_MANAGER`/`ADMIN`, "Admin" moved from last to right after
  "Dashboard" in the top nav, the account dropdown, and the mobile menu —
  their primary duty, not an afterthought at the end of the list.

- **App-wide dark mode.** A new `lib/theme.tsx` `ThemeProvider` (mirroring
  `lib/i18n.tsx`'s provider/hook shape) toggles a `.dark` class on `<html>`,
  detected from `prefers-color-scheme` on first visit and persisted to
  `localStorage` after that, with a toggle button (`components/shared/
  theme-toggle.tsx`) next to the language switcher in the navbar (desktop
  and mobile). Because every existing color in this app already flows
  through the CSS custom properties in `index.css` (`--ink-navy`,
  `--paper`, `--cloud`, `--hairline`, ...) rather than being hardcoded, a
  single new `.dark { }` block redefining ~15 base tokens re-themes
  essentially the entire UI with no per-component changes — see the new
  comment in `index.css` explaining why redeclaring the derived shadcn
  tokens (`--background`, `--card`, `--ring`, ...) individually isn't
  needed. The handful of components using a raw Tailwind palette color
  instead of a token (status badges, warning/error banners, the
  destructive dropdown/button hover) got explicit `dark:` variants;
  purely decorative mid-tone icons (star rating, favorite heart, trophy)
  were deliberately left as-is since they read fine unchanged in both
  modes. Also sets `color-scheme` (light/dark) so browser-rendered chrome
  — the date-input calendar glyph, scrollbars — follows the theme instead
  of staying stuck on its browser-default dark rendering, which was
  otherwise nearly invisible against a dark input.

### Changed

- **Complete UI/UX remaster of the frontend ("court-side precision").** A new
  design system documented in the new root `DESIGN.md` (synthesised from
  Refero's Linear/Ramp/Wise/Vercel styles): chalk canvas, ink type, a single
  optic-lime brand accent, Geist + Geist Mono, hairline elevation, semantic
  status tokens that re-theme in dark mode, motion tokens with reduced-motion
  support, and a new tennis-ball logo/favicon. Every page and shared
  component was rebuilt on it:
  - **App shell**: signed-in pages now live in a sidebar layout (grouped
    navigation with live unread/approval badges, a persistent "Book a court"
    action, a ⌘K command menu for pages/courts/actions) with a mobile drawer;
    court browsing adapts to the shell when signed in.
  - **Dashboard**: a "Needs your attention" strip (holds with live countdown
    + confirm, waitlist offers, games to rate), a "Next up" hero for the next
    confirmed game, reservations split into Upcoming / History / Calendar
    grouped by day (previously one unsorted list mixing cancelled and
    expired bookings), and a side column with season stats, open games,
    shared bookings, waitlist, teammates and community activity.
  - **Booking**: a guided court → day → slot flow with a day strip, slots
    generated from the court's real opening hours (was a hardcoded 07–22
    dropdown), morning/afternoon/evening groups, a sticky price summary, a
    "slot held" dialog with a live countdown and one-click confirm, waitlist
    straight from a taken slot, and today skipped automatically once it's
    over. Court detail pages deep-link a chosen slot into it.
  - **New pages**: Open games (`/app/games`) and Settings (`/app/settings`,
    account, public profile, notifications, calendar sync, appearance) split
    out of the old profile tabs; Community (`/app/players`) gains Feed /
    Players / Leaderboards tabs.
  - **Admin**: split into one file per tab; an approval queue with inline
    approve/reject on the overview, single-series charts with tooltips,
    a searchable reservations table with status counts, pagination and
    row actions, searchable/sortable users with a no-show flag, court
    utilisation heatmap, upcoming/past facility blocks with reason presets.
  - **Everything else** (courts, court detail with gallery lightbox and
    rating distribution, profile, player profile, teams, chat with date
    separators, grouping and an auto-growing composer, landing, help with a
    sticky table of contents, about, contact, auth with inline validation and
    password strength, 404) redesigned with designed loading/empty/error
    states and mobile layouts.

- **Browser push notifications are now sent after the change is saved, with
  retries (C03, ADR-005).** `notify()` used to call the push service
  synchronously inside the request's transaction — while holding the
  reservation's row lock and before commit, so a slow push service delayed
  competing Cancel/Approve/expiry, and a push could announce a change that
  then rolled back. Pushes are now queued in a `push_deliveries` outbox in
  the same transaction and sent by a 5 s background dispatcher
  (`push_delivery.py`, the only `pywebpush` user) with retry/backoff;
  pushes may arrive a few seconds later than before. Both background loops
  now run off the event loop. New table only — `create_all` creates it.

- **Every primitive UI component now sources from the real shadcn/ui CLI
  registry instead of being hand-rolled.** `components/shared/{avatar,badge,
  button,card,dialog,dropdown-menu,input,label,select,separator,skeleton,
  sonner,switch,tabs,textarea}.tsx` moved to `components/ui/` and were
  regenerated via `npx shadcn add <name>` (`components.json` added), with
  this app's design-token classes, custom variants (e.g. `Button`'s `dark`
  variant), and previously-fixed bugs (e.g. `Tabs`' tab-bar overflow fix)
  ported forward onto the regenerated files rather than discarded — a raw,
  unmodified CLI drop-in would have reverted those to shadcn's generic
  neutral-gray defaults. The app now depends on the unified `radix-ui`
  package instead of per-primitive `@radix-ui/react-*` packages. No visual
  or behavioral change for users — verified by screenshotting every major
  page/state (landing, auth, courts, dashboard, profile, admin, dialogs,
  dropdowns) before and after. See `component-design` for the pattern to
  follow when adding a new primitive.

### Fixed

- **Dates, times and relative times now follow the selected language.**
  Formatters were hardcoded to `en-GB`/`en`, so Czech users saw English
  weekday/month names and "2 hours ago"; everything now goes through a
  locale-aware `useFormatters()`.
- **Reschedule dialog prefilled the wrong day near midnight** (it mixed a UTC
  date with a local time).
- **Review avatars, last-message times in chat, actor names in reservation
  history and the cost-split per-person figure** were returned by the API but
  never shown.

- **`PlayerSearch`'s result dropdown was broken inside every `Dialog` that
  used it** ("New message" in Chat, "Invite a player" on a reservation
  card) — a `position: absolute` overlay inside a `Dialog`'s
  `overflow-y-auto` content box gets treated as extra *scrollable* height
  rather than shown as a floating layer, so results rendered off-screen
  and needed scrolling the whole dialog down to reach. Rebuilt as an
  inline, in-flow list directly under the search input instead of a
  floating overlay — the simpler shape avoids that failure mode outright
  (nothing to clip, nothing to escape a scroll container for), rather
  than fighting it with an escape-hatch (a portal + fixed positioning was
  tried and hit a second failure mode — Radix `Dialog`'s modality guard
  marks everything outside its own portal `inert` while open, which
  included a separate portal). Both dialogs using it (`ChatPage.tsx`,
  `reservation-card.tsx`) were also widened (`max-w-md` → `max-w-lg`) and
  given a `DialogDescription`, since a name-search list needs more room
  than a bare input did.
- **The occupancy timeline's legend overlapped itself on `/book`.** Time
  labels ("07:00"/"22:00") and the four status-dot legend items shared one
  `justify-between` row with no minimum gap between them; on `/book`'s
  narrower sidebar card (`max-w-4xl` vs. `CourtDetailPage`'s `max-w-5xl`,
  where the same component happened to fit) the two ends collided with
  the legend group with zero spacing. Split into two rows — times on one,
  a `flex-wrap`-capable legend on the next — so it can never collide
  regardless of container width.

## [0.2.0] - 2026-09-23

### Fixed

- **Five pages were missing the app's page-shell convention entirely** —
  `mx-auto max-w-*xl px-6 py-16` plus a `SectionHeader` (eyebrow + big bold
  title + description), which every other page (Courts, Dashboard, Profile,
  Admin, Court detail, Book a court) already uses. `/app/players`,
  `/app/teams`, a team's detail page, and a player's public profile instead
  rendered a plain `<h1>` flush against the browser's edge with no gutter
  or max-width, and `/app/chat` had no page padding at all — the four
  looked like an unfinished fragment of the app next to every other page,
  not a deliberate visual difference. Found by direct comparison against
  the rest of the app rather than the earlier per-page UI audits, which
  each looked at pages individually and missed that these four had never
  been brought in line with the shell every other page converged on.
  Fixed by applying the same container + `SectionHeader` (or, for Chat's
  legitimately different full-height split-pane layout, the same page
  gutter without forcing it into a card-grid shape it shouldn't have).
- **Achievement icons switched from emoji to Lucide**, matching every other
  icon in the app (sport icons, activity-feed icons, stat tiles). The
  Achievements tab, a player's public profile, and the activity feed's
  "unlocked an achievement" entries all previously rendered a raw emoji
  (🎾, 🏆, 🦋, ...) next to otherwise-Lucide UI — a visual inconsistency
  flagged during the UI polish audit and confirmed with the user rather
  than resolved unilaterally, since it was a genuine style call. New
  `components/shared/achievement-icon.tsx` maps each achievement's `key` to
  a specific Lucide icon (e.g. `Flame` for a play streak, `Compass` for
  visiting different courts); the backend's `Achievement.icon` emoji field
  is unchanged and still returned, just no longer rendered by the frontend.

### Added

- **UI polish pass, round 2 — a second mobile-overflow bug in the
  Dashboard's own layout, plus smaller fit-and-finish fixes** found by
  re-verifying round 1's fixes in a real 375px viewport rather than trusting
  them on sight:
  - **Dashboard's two-column layout (`grid-cols-[1fr_320px]`) overflowed the
    viewport below `lg`** even after round 1's tab-bar fix — CSS Grid's
    `min-width: auto` default meant neither the reservation-list column nor
    the sidebar would shrink below its own content's intrinsic width.
    `document.documentElement.scrollWidth` measured 422px against a 375px
    viewport; adding `min-w-0` to both grid children brought it back to
    exactly 375px. This also explains why the round-1 tab-pill fix wasn't
    fully effective on this page — it was resolving against an
    already-oversized parent. The view-mode tab bar itself (List/Calendar/
    Find a partner/Feed) also picked up `overflow-x-auto` and `shrink-0` so
    it scrolls instead of wrapping oddly on narrow screens, and the stat-tile
    row now uses a 2-column grid on mobile instead of stacking to one.
  - **Admin's Availability tab**: the block-a-court "From"/"To" datetime
    inputs sat side-by-side unconditionally, squeezing to unusable width on
    mobile — now stack to one column below `sm`. The block-list cards had no
    max width and stretched uncomfortably wide on a large desktop viewport —
    capped at `max-w-xl`, matching the form column beside it.
  - **Admin's Users tab**: the role `<Select>` was too narrow (`w-40`) for
    "Správce sportoviště" (Czech for "Venue manager") to fit on one line —
    widened to `w-48`.
  - **Courts page's "All courts" section duplicated every card already
    shown above it** in Trending/Recommended — with the seeded demo
    catalog's small size, that meant nearly every court printed twice on
    the page. Now filters "All courts" down to courts not already curated
    above, and hides the section entirely rather than showing an empty grid
    when nothing's left to show.
- **UI polish pass, round 1 — a real shared-component bug, a real mobile
  overflow bug, and design-token cleanup.** A full visual audit of every
  page (4 parallel passes, desktop + mobile) against the existing "navy
  ink on cool marble" system found two genuine, reproduced defects and a
  batch of small consistency fixes:
  - **`TabsList` (`components/shared/tabs.tsx`) had no overflow handling.**
    On a narrow screen, a page with enough tabs (Profile's 7, Admin's 6)
    grew wider than the viewport with no scroll container, and activating
    an off-screen tab auto-scrolled the whole page horizontally — every
    panel on the page shifted with it, independently reproduced by two
    separate audit passes (Admin: 2 of 6 tabs completely hidden; Profile:
    tab content rendering with a large negative horizontal offset, verified
    via `getBoundingClientRect()`, not a screenshot artifact). Fixed at the
    shared-component level (`overflow-x-auto` + `max-w-full`), benefiting
    every tabbed page at once; Profile additionally got the same
    edge-bleeding scroll wrapper Admin already had, for a consistent feel.
  - **`court-card.tsx`'s plain (`onSelect`) variant — used in Book a
    court's court list — genuinely overflowed the viewport at 375px** when
    a card had enough content (the `requires_approval` badge + a rating
    line): `document.documentElement.scrollWidth` measured 400px against a
    375px viewport. The text content block had no `min-w-0`, so the
    non-shrinking price pushed past the card edge instead of wrapping.
    Fixed with `min-w-0`/`flex-wrap`/`truncate`, verified back to exactly
    375px.
  - Chat: a short conversation's messages floated near the top of the
    scroll area with a large empty gap before the composer instead of
    sitting just above it; the per-message react/delete icon row was
    always fully visible, reading as slightly cluttered next to the rest
    of the app's cleaner styling — now dims to 60% opacity until hovered
    (or while its reaction picker is open).
  - Removed a duplicate Courtly logo on mobile Login/Register (the page
    navbar already shows one) and a stray `overflow-hidden` on
    About/Help's hero sections that clipped their decorative glow into a
    hard edge, inconsistent with how the same component renders
    everywhere else it's used.
  - **Design-token cleanup**: 20 occurrences of two literal hex values
    (`#e6f0ff`, `#eaf3ff`) across 15 files — a real violation of this
    project's own "never hardcode a hex color" rule — replaced with two
    new named tokens (`--tint-blue`, `--highlight-blue`) alongside the
    existing palette in `index.css`; two button hover-state hex literals
    got the same treatment (`--signal-blue-hover`, `--ink-navy-hover`).
    Zero visual change — same colors, now named and reusable instead of
    copy-pasted.
- **A second UX-completeness pass**, this time auditing in the direction
  the first one didn't: every backend endpoint checked for a real,
  reachable frontend consumer (not just every page checked against its
  own API calls). Found and fixed: a team join request could be sent but
  never cancelled (`cancelTeamJoinRequest` existed, had no button —
  Discover's "Requested" state is now a working "Cancel request"); the
  profile's Rating tab only ever showed one sport's leaderboard, with no
  way to see your own rating across every sport you'd played without
  cycling through each one (`GET /ratings/me` existed, had no caller — now
  a small "Your ratings" summary above the leaderboard). Also closed
  content gaps a second pass over previously-unaudited pages found: the
  landing page's "Why Courtly" section promised "the whole social side of
  showing up to play" while showing 0 of the 6 shipped social features —
  added teams, chat, and rating/challenges tiles; the Help Center gained
  a favorites entry (never covered) and an admin-only-powers entry in the
  venue-manager section, and its recurring-facility-block description now
  actually says it's recurring.
- **Chat rebuild: delete, reactions, and photo attachments.** You can now
  delete your own message (soft-deleted — other participants see a
  "Message deleted" placeholder rather than the row just vanishing);
  react to any message with a fixed set of 6 emoji (tap again to remove
  your reaction); and attach a photo, with or without a caption, from the
  composer. All three are live over the existing chat WebSocket for every
  participant, the same as a new message already was. **Breaking for the
  dev database**: new `Message.deleted_at`/`image_url` columns and a new
  `message_reactions` table — run the drop/create/reseed cycle from
  `backend/CLAUDE.md`.
- **Teams rebuild: public discovery/join, a CAPTAIN role, and a team
  avatar.** A team is public by default (owner can flip it private from
  a new edit-team dialog); `/app/teams`'s new "Discover" tab lists public
  teams you're not already in, with a "Request to join" flow the owner or
  a captain accepts/declines from a new "Join requests" panel on the team
  page. A new `CAPTAIN` role (owner-promoted) can add/remove non-owner
  members and manage join requests, but can't delete the team, change its
  visibility, or touch another captain — those stay owner-only. Owners
  and captains can upload a team avatar, same compress-and-store pipeline
  as a user avatar/court photo/review photo. **Breaking for the dev
  database**: a new `TeamRole.CAPTAIN` enum value, a new
  `team_join_requests` table, new `Team.avatar_url`/`is_public` columns,
  and 3 new `NotificationType` values — run the drop/create/reseed cycle
  from `backend/CLAUDE.md`.
- **The players directory is now actually browsable**, not just a search
  box that returns nothing until you already know someone's name.
  `GET /users/search` with an empty/short `q` now returns a paginated
  list of public profiles instead of `[]`; `/app/players` shows it as a
  card grid with "load more".
- Team detail now shows when the team was created and when each member
  joined — both were already returned by the API, never rendered.
- The dashboard activity feed has a "Load more" button instead of being
  hard-capped at the most recent 30 events.
- **A venue manager's reservation queue and history now show what was
  previously hidden.** The admin reservation list includes each booking's
  guests (previously only the booker was visible — a real gap for
  resolving a group check-in/no-show dispute), the reservation history
  dialog now shows who performed each action instead of just what
  happened, and a `PENDING`/`PENDING_APPROVAL` row shows its hold/approval
  expiry so the queue can be triaged by urgency. Court cards in the admin
  Courts tab now show the same star rating the public court page does,
  and a challenge card in the admin Challenges tab shows how many players
  have completed it.
- **Recurring bookings are now visibly marked as a group.** A "Recurring"
  badge on `ReservationCard` and the reservation detail dialog when a
  reservation belongs to a series — previously all 8+ weekly occurrences
  looked like unrelated one-off bookings.

- **Help Center coverage for the "Courtly Communities" features.** Chat,
  teams/clubs, player profiles/follow, skill rating and the leaderboard,
  seasonal challenges, the activity feed and review photos were all
  shipped without ever being added to the Help Center — the "Playing with
  others" section and FAQ now cover all of them.
- **A "Recent games" section on player profiles.** The last 5 `COMPLETED`
  reservations a player was part of (as booker or accepted guest), with
  court/sport/date; a 1-on-1 game with a reported match result also shows
  the opponent and win/loss/draw. Respects the existing profile-visibility
  gate — hidden whenever the rest of a private profile's stats are.
- **Photos when writing a review**, not just afterward. Review photos
  shipped earlier (up to 4 per review, shown on the court detail page)
  but the only way to attach one was to add it after the fact from
  Profile → My reviews; the "Rate it" dialog now has the same picker at
  creation time too.
- **Player search and a players directory** (`/app/players`, navbar
  "Players" link). `GET /users/search?q=` matches public profiles by name
  (an exact email match still resolves a private profile, same as before)
  — this is what actually makes the profile pages from the "Courtly
  Communities" epic discoverable instead of only reachable by stumbling
  onto a link.
- **Public player profiles and follow.** A profile page per player
  (`/app/players/:id`) showing bio, achievements, skill ratings and a
  follow button; a profile is public by default with an opt-out toggle,
  which hides bio/stats (not name/avatar) from everyone but the owner.
  **Breaking for the dev database:** new `User` columns and a new
  notification type — run the drop/create/seed cycle from `backend/CLAUDE.md`.
- **Review comments.** Any signed-in player can reply to someone else's
  review, not just its author — the existing "helpful" vote already
  covered reactions, this adds the discussion half.
- **Real-time chat** — direct messages, a group chat per reservation, and
  a group chat per team, delivered live over a WebSocket
  (`/ws/chat`; see ADR-004) with REST as the fallback/history path. A
  navbar icon shows a live+polled unread badge.
- **Persistent teams/clubs**, each with its own roster and group chat
  reusing the chat infrastructure above. Membership is added by email
  (owner only); a removed member loses chat access immediately, unlike a
  reservation guest. **Breaking for the dev database:** a new `Conversation`
  column and a new notification type — run the drop/create/seed cycle.
- **Match results and skill rating.** Either participant of a completed,
  1-on-1 (exactly one guest) booking can report a win/loss/draw; ratings
  update with a standard Elo formula, surfaced on player profiles and a
  new sport-filterable leaderboard tab. Group bookings aren't rateable —
  there's no well-defined winner/loser pairing without a team-assignment
  UI this didn't seem worth building. **Breaking for the dev database:**
  a new notification type — run the drop/create/seed cycle.
- **Seasonal challenges.** A venue manager can run a time-boxed goal (e.g.
  "play 10 sessions this autumn") from the admin panel; players see
  progress bars on their profile. **Breaking for the dev database:** a new
  notification type — run the drop/create/seed cycle.
- **Activity feed** — a 4th tab on the dashboard showing what players you
  follow have been up to (followed someone, joined a team, played a
  rated match, completed a challenge or achievement, opened a game to
  join).
- **Web push notifications.** A "Browser notifications" toggle on the
  profile page delivers the same notifications to the browser via a
  service worker, even when the tab isn't open, respecting the existing
  per-category mute preferences.
- **Review photos** — up to 4 photos per review, shown publicly on the
  court detail page.
- **Recurring facility blocks.** A venue manager can repeat a maintenance
  block weekly (2–26 weeks) and remove every occurrence at once.
  **Breaking for the dev database:** a new `FacilityBlock` column — run
  the drop/create/seed cycle.

- **A new `ADMIN` role, above `VENUE_MANAGER`.** Inherits every venue-manager
  capability, plus two admin-only ones: changing anyone's role — including
  granting or revoking `ADMIN` itself (a venue manager keeps the existing
  player ↔ venue-manager toggle only) — and permanently deleting a court
  that has no reservation history (`DELETE /courts/{id}`; deactivating is
  still how you retire a court that's actually been used). The Admin →
  Users tab is now a role picker instead of a promote/demote toggle, with a
  confirmation step for anything touching the admin tier. The seeded demo
  venue-manager account is now the demo admin account
  (`admin@courtly.app`); a new `manager@courtly.app` demo account covers
  the venue-manager tier. **Breaking for the dev database:** a new enum
  value — run the drop/create/seed cycle from `backend/CLAUDE.md`.
- **Approval process for courts that require it** (C02, spec v0.2). A court can
  be flagged `requires_approval`; on it a player's Confirm submits the
  reservation (`PENDING_APPROVAL`, blocks the slot for up to 24 h or until the
  start) and a venue manager approves or rejects it (`POST /reservations/{id}/approve|reject`);
  undecided requests expire. Includes the manager approval queue in the admin
  panel, the court setting, "awaiting approval" everywhere reservations are
  shown, and in-app notifications for both sides (English/Czech).
  **Breaking for the dev database:** new columns and enum values — run the
  drop/create/seed cycle from `backend/CLAUDE.md`.
- `GET /courts/{id}/availability/check` — a yes/no answer (with cause) for one
  exact interval, including facility blocks.
- `docs/specification-v0.1.md`, `docs/specification.md`, `docs/change-c02-impact.md`
  — the executable specification of the reservation operations; its
  verification examples run as `test_spec_baseline.py` / `test_approval_api.py`.

- Team Git workflow: branch → PR → merge lifecycle is now Claude's default
  for meaningful changes, driven by `finish-task`, with a hook guarding
  against direct commits to `main`.
- This changelog.
- A public **Help Center** (`/help`), linked from the navbar and footer on
  every page: a getting-started walkthrough, how booking/holds/approval/limits
  work, a plain-language glossary of every reservation status, the social
  features (open games, guests, split cost, teammates), staying-on-top-of-it
  tools (waitlist, calendar sync, recurring bookings, reschedule), a
  venue-manager guide, and a full FAQ — in English and Czech.
- A landing-page "Why Courtly" section surfacing features that existed but
  weren't visible from the homepage (open games, waitlist, split cost,
  calendar sync, recurring bookings, achievements), an FAQ teaser, and a
  venue-manager callout linking into the new Help Center.
- `components/shared/error-state.tsx` — a shared "this failed to load, retry"
  state (the `isError` sibling of `EmptyState`), now wired into every page's
  primary data queries (dashboard, profile tabs, admin tabs, courts, book a
  court) — those previously rendered nothing on a failed request instead of
  an actionable error.

### Changed

- Inviting a guest to a reservation and adding a team member now search
  players by name in the UI instead of requiring their exact email
  address; both endpoints accept a `user_id` as an alternative to
  `email` (email still works, e.g. for a private profile you already
  know the address of).
- Gallery/list photos (court grids, admin/profile galleries, leaderboard
  and teammate avatars) now lazy-load instead of downloading immediately;
  the one true hero photo per page still loads eagerly. Uploaded files
  under `/static/*` are now cached indefinitely by the browser (safe
  because an upload never gets overwritten in place, always a fresh
  filename).
- A reservation can only be cancelled before its start time, from `PENDING`,
  `PENDING_APPROVAL` or `CONFIRMED` (previously any time, and from `CHECKED_IN`);
  the UI only offers Cancel when it will work.
- Whole-application UI/UX pass: `ReservationCard`'s up-to-six equal-weight
  action buttons are now one primary action plus a "more actions" menu;
  Dashboard reflows into a main column (reservations) and a secondary column
  (teammates/waitlist/join requests/shared-with-you) instead of one long
  single-column stack, with a shared `data-row.tsx`/`subsection-heading.tsx`
  primitive replacing six ad hoc copies of the same row/heading markup
  (also applied across Admin's reservations/users/availability tabs); the
  authenticated `/app/*` shell now shows a slim footer instead of the full
  marketing one; dialogs cap at 85vh with internal scroll so a long one
  (the admin court form) never pushes its Save button off-screen; `Input`/
  `Textarea` gained a shared `aria-invalid` styling hook; the booking-summary
  card on Book a court/Court detail is sticky on desktop; Courts' filtered
  empty state offers a "Clear filters" action; the 404 page has real (i18n'd)
  copy instead of hardcoded English court-themed text, plus a second action;
  a few remaining hardcoded `aria-label`s (star rating, password show/hide,
  mobile nav toggle) are now translated.

### Fixed

- **A private profile's follower/following list is no longer readable by
  anyone signed in.** `GET /users/{id}/followers`/`/following` never applied
  the same visibility gate `get_player_profile` already uses for
  bio/stats — found during a UX audit of the social pages, fixed
  alongside it since it's the same file and a two-line permission check.
  Follower/following *counts* are unaffected (same as most social apps,
  a private account's counts are still visible, only the list isn't).
- **A facility-maintenance block is now visible before you try to book it.**
  `GET /courts/{id}/availability` only ever reflected reservations, never
  `FacilityBlock`s, even though booking into a blocked window was already
  rejected server-side — a slot could look free on the occupancy timeline
  and the start-time picker, then 409 at submit. The timeline and picker
  now show it as a distinct "Unavailable" state (with the manager's reason
  on hover), separate from a genuinely booked slot.
- A court that `requires_approval` is now flagged on its detail page and in
  the "Book a court" court list, not just after you've already picked it
  and reached the confirm step.
- Clicking a "added to a team," "match result reported" or "challenge
  completed" notification no longer goes nowhere, and all three can now be
  muted from Profile → Notifications — the frontend's `NotificationType`
  list had drifted out of sync with the backend's since the PRs that added
  them.
- Confirming a hold whose 5 minutes had passed (but was not yet swept), or on a
  court that was deactivated, no longer succeeds.
- A late Confirm can no longer overwrite a Cancel that won the race, and the
  same holds for Approve/Reject/expiry (state changes now take a row lock).
- A `end_time` without a timezone offset returns 422 instead of a server error.
- The personal calendar feed no longer shows an unapproved request as confirmed.

