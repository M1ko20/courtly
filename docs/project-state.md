# Project State

This file is a **state index**, not a source of truth for requirements —
it exists so a new session doesn't have to re-derive "where are we" from
scratch. It records *what phase the project is in* and *what's evidenced*;
it does not define *what the rules are* (that's `docs/specification.md`)
or *what the course requires* (that's `docs/course/`).

**Keep this file current.** Any workflow in `.claude/workflows/` that
completes a phase, an operation, or a gate item updates this file as its
last step. If you finish work that changes the picture below and don't
update this file, the next session will start from a wrong premise.

---

## Current phase

**C01–C06: all DONE. C07–C08: in progress** (assignment `docs/course/C07-C08.md`;
CP1 defence (A + C) on the exercise right after C07, not a week later). **C01: DONE.** **C02: DONE**: the team
approved specification baselines v0.1, v0.2 and v0.3 on 2026-10-12, which
was the last open gate. **C03: DONE**: Part A
(AS-IS trace) and B–M (drivers → ADR-005 → TO-BE views → outbox implementation
→ verification) for Confirm Reservation, evidence in `docs/evidence-and-evolution.md`.
**C04: does not exist.** C03 took its place in the course, so there is no
C04 assignment and nothing to track. **C05: DONE**: detailed design of the
Reservation Lifecycle. **C06: DONE**: we assessed another team's project
(team member Marek Tyl, GitLab MR `danielkodrla/swi!6`, 2026-10-19), and team HAH assessed
ours (`v4.1.0`). Both of HAH's verified findings are dispositioned and closed in `v4.1.1`.

| | |
|---|---|
| C01 | **DONE** — all 15 `docs/course/C01.md` §10 items evidence-backed complete |
| C02 | **DONE**. Baseline v0.1 and the "approval process" change (v0.2) are engineering-complete and evidenced, and both were approved by the team on 2026-10-12 (§11 of `docs/specification-v0.1.md` and `docs/specification-v0.2.md`) |
| Specification baseline | v0.3 — `docs/specification.md` (2026-10-08: venue-scoped managers, ADR-008), approved by the team on 2026-10-12. The C02 baselines are frozen: v0.1 in `docs/specification-v0.1.md`, v0.2 in `docs/specification-v0.2.md` |
| C03 | **DONE** (assignment: `docs/course/C03.md`). Part A + B–L in `docs/architecture-and-decisions.md` (§ "C03 Part A", § "C03 — Architecture", ADR-005); evidence (M) in `docs/evidence-and-evolution.md` § "C03 — Architecture Evidence". Commit/tag: implementation merged to `main` in PR #71 (`da3158d`), tag `c03-architecture`. Follow-up 2026-10-08 (PR #76): waitlist accept, the one path that bypassed the Lifecycle, now goes through it (amendment at the end of `docs/architecture-and-decisions.md`). No C03 item open |
| C04 | **Does not exist**: C03 took its place in the course (stated by the team, 2026-10-12) |
| C06 | **DONE** (assignment: `docs/course/C06.md`). Assessed by HAH on `v4.1.0`; owner disposition (F1, F2 accepted and fixed, F3 rejected candidate) in `docs/evidence-and-evolution.md` § "C06 Internal Evidence Assessment"; fixes in tag `v4.1.1` |
| C07–C08 | **IN PROGRESS** (assignment: `docs/course/C07-C08.md`). Today's part (verified C06 decisions): done, same section. B Risk Assessment: `docs/evidence-and-evolution.md` § "Risk Assessment" (6 risks, 5 categories). A Technical Design Review and C Status Report (6-slide PPTX): prepared outside the repo, reporting baseline `v4.1.2`; open until presented |
| C05 | **DONE** (assignment: `docs/course/C05.md`). Detailed design of the Reservation Lifecycle (C03 R2) in `docs/architecture-and-decisions.md` § "C05 Detailed Design"; tests DD-T1…DD-T9 in `backend/tests/test_lifecycle.py`; evidence (tests, design ↔ code comparison, remaining risk) in `docs/evidence-and-evolution.md` § "C05 DD Verification Evidence". Tag `c05-detailed-design`. No C05 item open |

## Completed gates

Evidence-backed only — each line names where the proof actually lives, not
just an assertion. Cross-referenced against `docs/course/C01.md` §10 and
`docs/course/C02.md`'s "Definice hotového" checklist; this table does not
restate those checklists, it tracks status against them.

**C01 (all 15 items, `docs/course/C01.md` §10):** complete. Evidence: PR
[#5](https://github.com/tylmarek1/C01/pull/5) merged 2026-09-14 (reviewed
by a non-author per the C01 review-cycle requirement),
`docs/evidence-and-evolution.md`'s "C01 Engineering Spike" section (all
four fields filled), `docs/intent-and-change.md` (Project Frame, all
fields filled including the Q future pressure). (Root `README.md` no
longer carries its own copy of this per-item checklist — the C01 course
checklist itself lives in `docs/course/C01.md` §10 and status against it
is tracked here, not duplicated in the product README.)

**C02 baseline v0.1 (`docs/course/C02.md`, "A. Baseline v0.1," items
1–11):** complete. Evidence: `docs/specification-v0.1.md` §1–10 (all four operations fully
specified, §6 requirement acceptance review, §7 consistency review, §5
use-case/state/activity diagrams); `backend/tests/test_spec_baseline.py`
(43 tests, all VE-01…VE-04); `docs/evidence-and-evolution.md`'s "Evidence
C02" section (success + negative/boundary run of all four operations,
commit `76c99ba`).

**C02 change "approval process" (`docs/course/C02.md` items 12–16):**
complete. Evidence: `docs/change-c02-impact.md` (impact analysis, written
*before* the spec edit — item 10 — with affected/unaffected parts
explicit — item 11); `docs/specification.md` §4 OP-05/OP-06 (fully
specified — item 12), §5.1/§5.2 (updated diagrams — item 13);
`backend/tests/test_approval_api.py` (38 tests, VE-05…VE-08 — 37 from the
v0.2 change plus VE-06.2, added in this repository's own governance pass
to close a spec↔test gap);
`docs/evidence-and-evolution.md`'s "Evidence C02" section (live run,
`change-c02-impact.md` §3 architectural drivers AD-1…AD-6 — item 16).

**Team approval of the specification baselines** (`docs/course/C02.md`
"Definice hotového"; v0.3 as well): complete on 2026-10-12. Evidence: all
four members are ticked, with the date, in §11 of
`docs/specification-v0.1.md`, `docs/specification-v0.2.md` and
`docs/specification.md`. This was recorded on team member Vrána's
statement that the whole team approved. As a result, item 14 of
`docs/course/C02.md`'s DoD ("running app matches the *approved* baseline
v0.2") now holds formally, not just behaviourally.

**C03** (`docs/course/C03.md`): complete. Evidence:
`docs/evidence-and-evolution.md` § "C03 — Architecture Evidence", tag
`c03-architecture`.

**C05** (`docs/course/C05.md`, all 12 DoD items): complete. Evidence:
`docs/architecture-and-decisions.md` § "C05 Detailed Design",
`docs/evidence-and-evolution.md` § "C05 DD Verification Evidence"
(9 DD tests, 487 passed), PR #91, tag `c05-detailed-design`.

## Pending / open gates — needs human action, not more code

- **C07–C08 / CP1:** the defence itself (A + C) at the next exercise, and the
  risk treatment that is still NOT VERIFIED (`docs/evidence-and-evolution.md`
  § "Risk Assessment", R-01: each member's clean run + dry run, due 2026-11-16, i.e. after the defence). They are open until a team member
  does them. A session must not mark them done.
- The specification-baseline approval gate was closed on 2026-10-12 (see "Completed gates").

## Architectural drivers carried into C03

From `docs/change-c02-impact.md` §3 (full detail and code evidence there —
don't restate it here, it will drift). C03 refined them into DR-1…DR-4
(`docs/architecture-and-decisions.md` § "C03 — Architecture" B); ADR-005
addresses AD-5 for Web Push and narrows AD-3's lock scope.

AD-1 (long-lived persisted time-bounded process), AD-2 (blocking-state set
defined in four places — still open, see C05 "Remaining design risk"),
AD-3 (row-level serialisation is load-bearing), AD-4 (several doors to
`CONFIRMED`), AD-5 (notification delivery has no guarantees), AD-6
(approval authority was coarse — "any manager," not per-resource).

Status as of 2026-10-08: **AD-4 closed** — waitlist accept, the last path
around the Lifecycle, now goes through it (`docs/evidence-and-evolution.md`
§ "Follow-up 2026-10-08"; guarded by `test_only_the_lifecycle_changes_reservation_status`).
**AD-6 closed** — managers are scoped to their venues (ADR-008, spec v0.3
BR-10).

## Current assumptions and unknowns

Full register: `docs/specification.md` §8 (A-01…A-06, U-01…U-04). Not
restated here — this section exists only to flag that they exist and
where, so a session doesn't have to search for them.

## Latest verification

- `cd backend && uv run pytest -q` — **490 passed** against real
  PostgreSQL 16 (its own `reservations_test` database). Last run:
  2026-11-02, on release 4.1.1's code (the C07–C08 reporting baseline).
  The +3 since 4.1.0 are VE-05.3 on a normal court (C06 F1). A count is
  true only for this tag and date: on 2026-10-25 team HAH got 486 passed and 1 failed on
  `v4.1.0`, because one test depended on the season (C06 F2, now fixed).
- `v4.1.2` adds 8 cases (preconditions on both court kinds) and CI:
  `.github/workflows/ci.yml` (backend on PostgreSQL 16, frontend build +
  lint). First green run: PR #96. Under a moved clock (2027-06-15) the
  suite is 495 passed, 3 failed by the method, see `docs/evidence-and-evolution.md`
  "Follow-up 2026-11-02 — risk treatments".
  - The C02-baseline evidence figure stays **177 passed** (2026-09-21).
  - The suite later grew through product features (PRs #38–#44), the C03
    outbox (PR #71, 305) and the waitlist-lifecycle follow-up (PR #76, 309) and waitlist booking limits (311).
    None of these are C02 VE-xx tests or change C02's phase status.
- `cd frontend && npm run build && npm run lint` — build passes; lint shows
  only the 6 known `only-export-components` warnings. Last run: 2026-10-19
  (release 4.1.0; the fresh clone's `npm ci && npm run build` passed too).

## Latest evidence

`docs/evidence-and-evolution.md` — the C01 spike section, the
"Evidence C02" section, "C03 — Architecture Evidence" (with its
2026-10-08 follow-up) and "C05 DD Verification Evidence". That file is the durable evidence record; this
section just points to it.

## Latest relevant commit

Release **v4.1.2** (2026-11-02): frontend 4.1.0, backend 0.4.1, tag
`v4.1.2`, one baseline of docs, code, tests and CI (see `CHANGELOG.md`). It is
the C07–C08 reporting baseline. `v4.1.1` holds the C06 fixes. The C06 assessed baseline was `v4.1.0` (`4a23dc1`).
Course milestones:
- C02 engineering: PR [#9](https://github.com/tylmarek1/C01/pull/9) (`ede421d`).
- C03 architecture: PR [#71](https://github.com/tylmarek1/C01/pull/71)
  (`da3158d`), tag `c03-architecture`.
- C05 detailed design: PR [#91](https://github.com/tylmarek1/C01/pull/91)
  (`93af6a7`), tag `c05-detailed-design`.

---

## How to add the next course phase

Paste the assignment verbatim into a new `C0N.md` file under `docs/course/`, with the source
header used by `C03.md`/`C05.md`. Root `CLAUDE.md` §0's rule against
copying course text applies to every other file, not this one. Then add a
row to "Current phase" and, once its DoD items have evidence, an entry
under "Completed gates". The numbering skips C04: C03 took its place in
the course. Don't add content for a part the course hasn't handed out yet.

---

## How to update this file

A workflow updates the specific section its work affects — don't rewrite
the whole file for a small change. If a gate moves from pending to
complete, move its line and add the evidence pointer. If a new phase
starts, update "Current phase" and add a "Completed gates" entry for the
phase that just finished. Don't let this file accumulate historical
narrative — that belongs in `docs/evidence-and-evolution.md` or commit
history; this file only describes *now*.
