# Courtly (C01) — root CLAUDE.md

Courtly is a sports-court reservation system (tennis/volleyball/badminton).
It started as the **SWI** course's engineering-spike deliverable ("C01") and
was then expanded, at the team's own initiative, into a much fuller
product-style app. Team: VTG Courts (Adam Vrána, Marek Tyl, Josef Glogar,
Adam Mikoláš).

This file holds rules that apply regardless of which half of the repo you're
touching. Backend-specific and frontend-specific rules live in
`backend/CLAUDE.md` and `frontend/CLAUDE.md` — read the one that matches
what you're changing before you start. Don't duplicate those here.

**Operating principle:** the prompt is intent, the repository is context, the
skills are method, you provide judgment, the implementation is the result.
A short, high-level request ("add notifications," "make the frontend much
better") is not underspecified — it's normal. Investigate before asking;
decide what's inferable from the codebase yourself; ask only when a
decision is genuinely product-defining and the repository doesn't answer
it (see `feature-development`'s Step 1 for the line between the two).

## 0. Source-of-truth hierarchy

Six layers, strongest first for what each one owns. When two disagree,
resolve it explicitly and say which source was wrong — never silently
"fix" it by editing whichever file is easiest (`docs/definition-of-done.md`
has the fuller rule; `docs/evidence-and-evolution.md`'s "Nalezený nesoulad"
table is the worked example of doing this right, including cases where the
*docs* turned out to be wrong, not the code).

1. **`docs/course/`** — what the course actually requires, pasted verbatim
   from the assignment. Load the relevant `C0N.md` with the Read tool
   before any course-phase request (see "How work gets routed" below) —
   don't work from memory or from this file's summary of it. **Never**
   copy course text into this file, a skill, or `docs/project-state.md` —
   reference it by path.
2. **`docs/specification.md`** (+ `docs/specification-v0.1.md`, frozen) —
   the team's accepted behavioral baseline: operations, rules, states,
   diagrams. This is the requirement for business behavior. Skills and
   this file describe *how* to work, not *what the rules are* — don't
   restate a business rule here or in a skill, reference it by ID (`BR-xx`,
   `REQ-xx`).
3. **`docs/project-state.md`** — where the project is *right now*: phase,
   baseline version, completed/pending gates, architectural drivers,
   latest verification. A stateful index, not a requirements source.
4. **`docs/evidence-and-evolution.md`** — what was actually run and
   observed, dated and append-only; never rewritten to the present.
5. **`backend/src/`, `frontend/src/`, and the test suites** — what the
   system actually does right now. For "does this behavior exist today,"
   trust this over any doc.
6. **This file, `backend/CLAUDE.md`/`frontend/CLAUDE.md`,
   `.claude/workflows/`, and skills** — *how* to work here: process and
   convention, never a business rule that belongs in layer 2.

`docs/codebase-map.md` sits outside this numbering on purpose: it isn't a
source of truth for requirements or state, it's a navigation aid for
*where* things live and what they're responsible for — kept separate from
this file's *how to work* so neither grows into doing the other's job.
Read it early for orientation, keep it current per its own "Keeping this
current" section, and see `update-docs` for the trigger.

`docs/capability-map.md` sits outside the numbering the same way: not a
requirements source, a strategic map of engineering maturity (security,
testing, backend, frontend, product, the `.claude/` system itself) —
what's strong, weak, or missing, and the resulting backlog. It's updated
by `improve-app` (after a full audit) and `feature-development` Step 7
(a "valuable but separate" finding), not rewritten by hand each session.

Within layers 2 and 4, some files are **point-in-time records** — never
edit their substance to match newer code, only fix an actual error:
`docs/intent-and-change.md` (the Project Frame) and `docs/specification-
v0.1.md` are graded snapshots.
`docs/evidence-and-evolution.md` is append-only. `docs/change-c02-
impact.md` is a decision trail, not a description of today.
`docs/architecture-and-decisions.md` is append-only too: a changed
decision gets a new ADR or an "Amendment" note below the original, never a
rewrite in place. **Living** (should track current code):
`docs/specification.md` and root/`backend`/`frontend` `README.md` — a
mismatch you find there is a bug to fix via `update-docs`, not a
documented permanent gap.

Never re-quote a fact from one layer into another — a second hardcoded
copy is exactly how two docs independently drift (this has already
happened once: a skill's own "here's how stale the docs are" paragraph
went stale itself by hardcoding numbers the code then outgrew).

## How work gets routed

A short, high-level request is normal, not underspecified — investigate
before asking (see the Operating principle above). Match it to a workflow
in `.claude/workflows/`: plain procedure files, not skills — Claude Code
doesn't auto-discover them the way it discovers `.claude/skills/`, so this
table is how a short prompt actually finds one.

| Request looks like | Read |
|---|---|
| "dokonči C02" / "finish C02" / picking up course work | `docs/project-state.md` first (which phase, which gates are open), then whichever of `c01.md` / `c02-baseline.md` / `c02-change.md` that phase points to |
| "implementuj change z C02" / a new requirement change | `.claude/workflows/c02-change.md` |
| "C07/C08", "status report", "risk assessment", "obhajoba CP1" | `docs/course/C07-C08.md`, then `docs/project-state.md` (reporting baseline) and `docs/evidence-and-evolution.md` § "C06 Internal Evidence Assessment" / § "Risk Assessment" — update those in place, don't start a new document |
| "připrav mě na C03" | `docs/course/C03.md` if it exists yet (load it the same way as C01/C02); if it doesn't, say so explicitly and work from `docs/project-state.md`'s architectural-drivers list instead of guessing at C03's scope |
| "přidej X" / "add X" / "improve reservations" | `.claude/workflows/feature.md` |
| "oprav X" / "fix X" | `.claude/workflows/bug-fix.md` |
| "vylepši aplikaci" / "improve the app" / "find weaknesses" | `.claude/workflows/improve-app.md` |
| "kde jsme silní/slabí" / "what's our capability gap" / audit the engineering system itself | `docs/capability-map.md` first (current status + backlog), then `.claude/workflows/improve-app.md` if a fresh full audit is actually needed |
| preparing a hand-in, cutting a release | `.claude/workflows/release.md` |

A workflow orchestrates *order*; the skills table further down still does
the actual *how* for each step — a workflow names which skill applies
where, it doesn't restate that skill's content. For a non-trivial or
ambiguous request, briefly restate the scope you understood before making
sweeping multi-file edits, whichever workflow applies.

## Repository layout

```
docs/codebase-map.md                where modules/pages live and what they're responsible for — not a source-of-truth layer, a navigation aid (see below)
docs/capability-map.md              engineering maturity map + backlog — strong/weak/missing across security/testing/backend/frontend/product; not a source-of-truth layer either
docs/course/                        the course assignments, verbatim (C01.md, C02.md, ...) — layer 1
docs/project-state.md               current phase, gates, drivers — layer 3
docs/definition-of-done.md          the evidence-backed-completion rule (not a checklist)
docs/intent-and-change.md           Project Frame (domain, states, rules) — graded, still accurate as decisions
docs/architecture-and-decisions.md  ADR-000..010 (stack, exclusion constraint, repo split, JWT, WebSocket chat, Web Push outbox, Alembic, logging/audit, venues, opening hours/rates, payments); C03 Part A AS-IS trace + C03 architecture (Confirm Reservation); C05 detailed design (Reservation Lifecycle)
docs/evidence-and-evolution.md      the executed C01 spike write-up + the C02, C03, C05 evidence, the C06 owner disposition and the C07–C08 risk register
docs/specification.md               current specification v0.3 (approval process + venue-scoped managers); v0.1 and v0.2 (the C02 baselines) frozen in specification-v0.1.md / -v0.2.md
docs/change-c02-impact.md           impact analysis of the C02 change + architectural drivers handed to C03
.claude/workflows/                  the process files "How work gets routed" (above) points into
.claude/scripts/check-project-state.sh   structural check for this system — see "Mechanical checks" below
backend/                            FastAPI app — see backend/CLAUDE.md
frontend/                           React app — see frontend/CLAUDE.md
DESIGN.md                           the UI design system (tokens, components, patterns) — read before any UI change
docker-compose.yml                  single `db` service (Postgres 16) shared by both apps
```

## Stack overview

| | Backend | Frontend |
|---|---|---|
| Language | Python 3.12 | TypeScript |
| Framework | FastAPI + SQLAlchemy 2 | React 19 + Vite |
| Package manager | `uv` | `npm` |
| Data | PostgreSQL 16 (psycopg 3) | TanStack Query over a hand-written fetch client |
| Styling | — | Tailwind CSS 4 (CSS-first config) + Radix + shadcn-style components |
| Tests | pytest + httpx, against real Postgres | none exist yet (see frontend/CLAUDE.md) |
| Lint | not configured (a stray `.ruff_cache` is the only trace of ruff) | `oxlint`, default rules |

There is **no CI/CD** anywhere in this repo. That's the real current
state, not an oversight for you to silently fix — see "Known gaps" below.
Schema changes go through Alembic migrations (ADR-006, `backend/CLAUDE.md`). There is one narrow pre-commit hook (blocks commits
on `main`, see "Git workflow" below) plus the existing ruff-format
post-edit hook — neither is a substitute for CI.

## Cross-cutting architectural rules

- **Two toolchains, never mixed.** Backend is `uv`, frontend is `npm`
  (ADR-002 split them into separate directories on purpose so this stays
  unambiguous). Don't propose unifying them or running one from the other's
  directory.
- **PostgreSQL is load-bearing, not an implementation detail.** The "no
  double-booking" rule is enforced by a Postgres exclusion constraint
  (`no_overlapping_active_reservations`, see backend/CLAUDE.md), not by
  application code. Never suggest mocking or swapping the database, or
  moving the overlap check into Python "for simplicity" or "to make tests
  faster" — that would silently remove the actual concurrency guarantee
  ADR-001 exists to provide. Tests run against real Postgres for the same
  reason; that's deliberate, not a gap.
- **Every model change ships with an Alembic migration** (ADR-006).
  Autogenerate misses enum values and exclusion/check constraints — the
  details are in `backend/CLAUDE.md`; read it before changing a model.
- **C01–C03 boundary.** C01/C02 own requirements, domain behavior,
  evidence, and a working (not necessarily well-architected) walking
  skeleton; C03 owns architecture — `docs/course/C02.md`'s introduction
  says this directly (don't quote it here, read it there). If C02-phase
  work surfaces a real architectural question, record it as a driver in
  `docs/project-state.md` (see `docs/change-c02-impact.md`'s AD-1…AD-6 for
  the pattern) — don't solve it with premature structure unless the
  current requirement genuinely can't be met without it.

Find the real current code before proposing a change — don't assume a
README describes it (see §0). Look for an existing analogous pattern
before introducing a new one (`architecture-review`) rather than inventing
a parallel way to do something this codebase already does one way.

**A meaningful change owns its own Git lifecycle by default** — branch,
commit, push, PR, merge. You do not need to be asked for any of these
individually; see "Git workflow" below and `finish-task`, which drives
this lifecycle after implementation. The one thing that still needs an
explicit ask is a **destructive** git action (force-push, `reset --hard`,
deleting someone else's branch) — see the Environment's own Git Safety
Protocol for what counts.

## Definition of done

Two distinct passes, both before calling non-trivial work done:

- **`finish-task`** — the mechanical pass: picks the right test/build/lint
  commands for what you actually changed and confirms they pass. This repo
  has no CI, so this is the closest thing to one.
- **`self-review`** — the qualitative pass: reads the diff for correctness,
  architecture fit, security, performance, tests, UX, docs, and unnecessary
  changes.

### Review depth matches risk, not the number of skills available

Optimize for **engineering quality *and* low unnecessary token/session
spend** — not for maximum possible analysis. `self-review` (you, reading
the diff once) is the default and is usually the *entire* review; most
changes need nothing beyond it plus `finish-task`'s checks. Don't reach
for the built-in `/code-review` skill reflexively. When you do use it for
a normal feature/bugfix/change, the default is **low effort**, **0
subagents**, and **strictly scoped to the current diff and its directly
affected code paths** — never a repository-wide audit, and never invoked
bare (bare `/code-review` silently reuses whichever level was last used in
the session, which is how this went wrong once: a docs-only PR here
triggered a full multi-agent `/code-review` at an inherited `ultra` level
and burned a meaningful fraction of a weekly budget for a change
`self-review` alone was enough for). Escalate effort, or use up to 1–2
subagents, only when the change's actual risk justifies it — the table
below — and even then keep the review focused on the change and its
direct impact, not a broader sweep, unless a full audit was explicitly
requested. Review is proportional to **risk**, not to project size or how
many review-flavored skills happen to exist.

| Risk | Example here | Review |
|---|---|---|
| **Low** | UI copy, styling, a small component, docs, a small refactor | `self-review` only, then stop — 0 subagents |
| **Medium** | a typical feature, an API change, a multi-component change, ordinary business logic | `self-review` + `finish-task`'s checks; if an independent pass is genuinely useful, `/code-review low`, explicitly scoped to the diff — not a repo-wide audit. 0 subagents by default |
| **High** | reservation concurrency / the exclusion constraint, auth/authorization, a `lifecycle.py` transition, a database schema/migration change, a large cross-layer change | `self-review` plus a targeted read of the specific risk area (the relevant "Known pitfalls" entry, `security-review`/`database-evolution` as applicable); `/code-review` may escalate effort and/or use up to 1–2 subagents here, but stays scoped to the change and its direct impact |
| **Explicit / architectural full audit** | only when actually asked for one, or a change genuinely too broad to scope narrower | the full multi-angle `/code-review ultra`, or `improve-app`'s full audit mode |

Prefer a **targeted test over another review pass** wherever the risk is
mechanically verifiable — a business rule gets a test, not a second
read-through; a state transition gets a `lifecycle.py` test; a database
constraint gets the concurrency-style pattern already in
`test_persistence_spike.py`. A passing, meaningful test is stronger
evidence than another pass of eyes.

Don't run every skill for every change — `feature-development`'s Step 0
scopes which skills actually apply; a low-risk change doesn't need
`security-review`, `performance-review`, `architecture-review` and
`production-readiness` all run "just in case." Each already states when
it applies (that's the trigger, not "always run me"); trust it. This
applies to `/code-review` too, at any effort level: it reviews the change
in front of it, it does not go looking for a reason to pull in a broader
security/performance/production-readiness pass — only follow one of those
if something the diff itself actually touches genuinely calls for it. And
don't loop: `change → verify → review → fix if needed → verify → stop` — once
the change does what was asked, the relevant checks pass, and one review
pass found nothing left unfixed in scope, that's done; don't chain another
audit looking for more to find.

**If a review step finds a problem within the current task's scope, fix it
before reporting done — don't just list it.** "I found this but left it" is
only the right answer when the fix is genuinely out of scope, too large to
do safely right now, or itself needs a product decision — say which, don't
default to reporting over fixing.

**"Done" means evidence-backed, not "looks complete."** A gate, a
checklist item, or a feature is done only when you can point at a file, a
passing test, a command's actual output, or a human sign-off that proves
it — see `docs/definition-of-done.md` for the full rule, including the one
class of gate (a team's own sign-off on a specification) that a session
must *report as open*, never fabricate or silently mark closed. When a
change closes or opens something tracked in `docs/project-state.md`,
update it as part of finishing the change — don't leave the index
describing a phase that already moved on.

## Known pitfalls (grounded in real bugs, not hypothetical ones)

Every entry here has actually bitten this codebase once. Skills reference
this list rather than re-explaining each bug from scratch — if you find
yourself about to write a paragraph re-deriving why one of these matters,
link here instead.

1. **Naive UTC vs. venue-local time.** Comparing a wall-clock hour/minute
   directly against the `Europe/Prague` opening-hours rule rejected valid
   bookings from browsers in other offsets. Fix: `astimezone(VENUE_TZ)`
   before any hour/minute comparison. Regression-tested; don't reintroduce
   a naive comparison. (`backend/CLAUDE.md` §Timezones)
2. **i18n treated as "mostly done."** Pages have shipped with static
   English label maps and untranslated toasts because i18n coverage was
   treated as gradual. A page is complete-or-nothing: every string routed
   through `t()` before the page is considered finished, not deferred as
   "minor." (`i18n-check`)
3. **Frontend-only business-rule enforcement.** A lead-time check existed
   only in the booking UI, not the backend, and was caught by manual
   testing, not a review. A client-side check is a UX nicety; the backend
   (`rules.py`/`booking_validation.py`) is the only enforcement that counts.
   (`api-integration`, `security-review`)
4. **The exclusion constraint's status list going stale.** Adding a new
   reservation status that should still hold a court, without adding it to
   `no_overlapping_active_reservations`'s `WHERE status IN (...)` clause,
   silently removes double-booking protection for that status. A test
   (`test_the_exclusion_constraint_blocks_exactly_the_active_statuses`) now
   fails if the constraint and `ACTIVE_RESERVATION_STATUSES` disagree.
   (`database-evolution`)
5. **A schema change the migration doesn't carry.** Before Alembic,
   `create_all` silently skipped column/enum changes on existing tables.
   Autogenerate still skips enum values and exclusion/check constraints;
   `tests/test_migrations.py` fails on model↔migration drift and on a
   missing enum value. (`database-evolution`)

If you discover a new one of these while working, decide where it belongs
using the next section, and add it here only if it's genuinely a durable
trap — not every bug fix earns an entry.

## Where a new rule belongs — strongest enforcement wins

When you learn a new project-specific constraint (including one of the
traps above, or one you just found), prefer the strongest mechanism that
can actually enforce it, in this order:

```
mechanically enforceable (a lint rule, a type, a DB constraint, a hook)
        >
a skill's explicit instruction (loaded when relevant, actionable)
        >
CLAUDE.md prose (loaded always, costs attention forever)
        >
docs/README (reference material, not loaded automatically)
```

A rule a linter or the type system can enforce shouldn't live only as prose
someone has to remember. A rule that's only relevant to one kind of task
(e.g. "sweep for references before renaming a field") belongs in the skill
for that task, not in CLAUDE.md where it's dead weight on unrelated work.
CLAUDE.md prose is for constraints that are both durable *and* apply broadly
enough that every session needs them regardless of task. Don't invent
automation for its own sake — the `.claude/settings.json` ruff-format hook
exists because it was cheap and genuinely useful, not because "more
automation" is a goal in itself.

**Mechanical checks that exist today:** the ruff-format post-edit hook and
the `guard-main.sh` pre-commit/pre-push hook (both below); `finish-task`'s
test/build/lint commands; `.claude/scripts/check-project-state.sh`, a
structural check (not a content check) that `docs/course/`,
`docs/project-state.md`, `docs/definition-of-done.md`, and every
`.claude/workflows/*.md` this file's routing table points to actually
exist, and that this file hasn't absorbed a copy of the course text — run
it after touching any of those. None of this is CI (see "Known gaps") and
none of it checks whether a requirement is actually satisfied — only
reading `docs/course/` against `docs/project-state.md` does that.

## What belongs in CLAUDE.md (and what doesn't)

This file and the two below it load into **every** session on this repo —
they cost attention forever, so they only get durable constraints that would
silently break something if violated (a trap, an invariant, a "the tool
won't warn you" gap). Feature history, "we added X," and session narration
do **not** belong here — that's what commit messages and PR descriptions are
for. If you're about to add a sentence describing what a feature does rather
than a rule about how to safely change something, it probably belongs in a
README or docs file instead (see the `update-docs` skill).

## Git workflow (default, not optional)

`main` is protected by convention, and a hook backs that up mechanically
(see below): **never develop directly on `main`.** For any meaningful
change, the default lifecycle is:

```
branch → implement → verify (finish-task) → review (self-review) →
docs/changelog → commit → push → PR (gh) → merge → cleanup
```

Drive this yourself; the user shouldn't have to separately ask for a
branch, a commit, a push, or a PR — `finish-task` owns Steps after
implementation. Details:

- **Branch from `main`** (`git fetch origin && git checkout -b <type>/<short-desc>
  origin/main`) before touching files. Name it `feat/…`, `fix/…`,
  `refactor/…`, `perf/…`, `docs/…`, or `chore/…` per Conventional Commits.
  One logical task per branch.
- **Commits**: Conventional Commits style (`feat: …`, `fix: …`, `refactor:
  …`, `test: …`, `docs: …`, `chore: …`, `perf: …`), explaining *why* not
  restating the diff. Commit once the change verifies cleanly, not every
  intermediate edit.
- **Push and open a PR** with `gh pr create` once verification passes —
  this repo's remote is GitHub (`tylmarek1/C01`), not GitLab, so `gh` is
  the tool, not `git push` alone. PR description: what changed, why,
  affected areas, tests/validation run, notable decisions, risks — see
  `finish-task` for the exact template.
- **Author ≠ reviewer** in spirit — `self-review` (part of "Definition of
  done" above) is what satisfies this for most changes; it's you reading
  your own diff as if it were someone else's, not a rubber stamp. Escalate
  to the built-in `/code-review` skill only per "Review depth matches
  risk" above, with an explicit level — not reflexively before every
  merge.
- **Merge** with `gh pr merge` once checks/review are satisfied. This repo
  has no CI, so "checks satisfied" means `finish-task`'s own verification
  already passed on the branch — don't treat the absence of CI as license
  to skip that. Never merge a change you know is broken.
- **Cleanup** — delete the merged branch (`gh pr merge --delete-branch`, or
  `git branch -d`/`git push origin --delete` after merge) and sync local
  `main`.
- A **destructive** git action — force-push, `reset --hard` past the last
  push, deleting a branch that isn't the one just merged — still needs an
  explicit ask; it's the one thing this default lifecycle doesn't cover
  autonomously.

A pre-commit hook (`.claude/hooks/guard-main.sh`) mechanically blocks `git
commit`/`git push` while `main` is checked out, so forgetting to branch
fails loudly instead of silently landing on `main`.

## Security baseline

Auth is stateless JWT (HS256) + bcrypt password hashing (see
`backend/CLAUDE.md` for specifics). `SECRET_KEY` has an insecure default
fallback — that's a deliberate, documented local-dev convenience (ADR-003),
not a bug to "fix" by hardcoding a different secret; flag it if you're ever
asked to prepare this for anything beyond local development. Never log
tokens, passwords, or password hashes.

## Known gaps — flag, don't silently fix

No CI, no generated frontend API types, no frontend test suite.
These are real, current, and known. If closing one of these would
genuinely help the task you're doing, propose it and say why — don't
silently add a new dependency, config file, or pipeline as a side effect of
an unrelated change.

## Skills available in this repo

A skill is a competency — *how* to do one kind of thing well; a workflow
(`.claude/workflows/`, "How work gets routed" above) is a process — *what
order* to do things in for one kind of request, and which skills to use at
each step. Don't fold a whole project lifecycle into a skill (that's what
made `.claude/workflows/` necessary) and don't duplicate a workflow's
ordering logic inside a skill.

Skills live at three levels — Claude Code discovers them per-directory, most
specific wins, so a skill under `backend/.claude/skills/` or
`frontend/.claude/skills/` applies when you're working in that half of the
repo; the ones below apply everywhere.

| Skill | Use it when |
|---|---|
| `feature-development` | Any "add X" / "change X" request — the default entry point, classifies the change and drives the rest |
| `architecture-review` | Before adding a new module/file — does something existing already own this? |
| `finish-task` | Before declaring any non-trivial change done — picks the right checks to run, then owns commit → push → PR → merge → cleanup |
| `self-review` | Before declaring any non-trivial change done — qualitative diff read |
| `feature-completeness` | After implementing a feature, or "is X actually complete" — traces the whole feature end-to-end, not just the diff |
| `consistency` | Before adding a new endpoint/component, or asked to review consistency — follow existing conventions, flag drift rather than adding a third variant |
| `improve-app` | "Improve the app," "find weaknesses," "what should we add," "find technical debt" — whole-application audit, can select a scope and implement it |
| `polish` | "Make X feel production-ready," "polish X" for a **named** feature/area — works → feels professionally built |
| `production-readiness` | "Make the application production-ready," "is this ready to ship" — blocking/important/nice-to-have gate |
| `schema-change-sweep` | Adding, renaming, retyping or removing a model field/table, a Pydantic schema, or a hand-maintained frontend type |
| `security-review` | Adding an endpoint/role logic, or asked to review/improve security |
| `performance-review` | Adding a data-heavy endpoint/page, or asked to review/improve performance |
| `refactoring` | Any "refactor/clean up/restructure" request |
| `versioning` | Deciding whether a change is breaking, bumping the version, and keeping backend/frontend/docs in step |
| `update-docs` | After a change that could make a README, `docs/*.md`, or `CHANGELOG.md` wrong |

Backend-only (`backend/.claude/skills/`): `api-design`, `database-evolution`,
`backend-testing` — see `backend/CLAUDE.md`.

Frontend-only (`frontend/.claude/skills/`): `component-design`,
`api-integration`, `accessibility-responsive`, `i18n-check` — see
`frontend/CLAUDE.md`.

**Skill system governance.** These are tools, not bureaucracy — don't invoke
every skill for every change (`feature-development`'s Step 0 exists
precisely to avoid that). Before adding a new skill, check whether an
existing one already covers the problem with a small addition instead; this
list grew by strengthening existing skills far more often than by adding
new ones, and should keep growing that way. Before adding an instruction
anywhere, run it through "Where a new rule belongs" above — most new
knowledge should extend a skill, not this file.
