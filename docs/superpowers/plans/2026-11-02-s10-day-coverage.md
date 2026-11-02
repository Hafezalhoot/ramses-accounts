# S10 cashier daily completion implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use test-driven-development and verification-before-completion in the current session.

**Goal:** Correct false 'incomplete' daily status when a collection point is deliberately off schedule, while preserving true missing shift alerts.

**Architecture:** Existing shift_coverage.report is the authoritative expected-windows module. Make only the day-summary consumer treat `not_required` as neutral and keep unknown/required shifts blocking. Human-readable UI status text only.

**Tech Stack:** Python 3, FastAPI, SQLite, vanilla JavaScript.

**Spec:** `docs/project-autopilot/S10_COVERAGE_CERTIFICATE_SPEC.md`

## Constraints / review focus

- No schema migration, financial postings, user role policy changes or productive deployment.
- Test zero required stations: must not falsely mark complete.
- Test unknown monitoring: must not falsely mark complete.
- Test required missing shifts: must remain provisional.
- Test a completed active point with non-operating points: must now be complete, while financially uncertified.
- Test report displays `not_required` legibly on full-coverage filter.

## Task 1: Daily coverage acceptance

- [x] Write failing synthetic FastAPI test `tests/test_s10_daily_coverage_certificate.py` covering owner authentication, effective weekday, off-day points, completed windows, missing windows, no financial writes and no claimed certification.
- [x] Run to prove RED on the off-day completed case.
- [x] Modify only `app.py:cashier_day_summary` aggregate to ignore `not_required` and require a non-empty set of genuinely required complete points.
- [x] Run GREEN test and key regression tests.

## Task 2: UI clarity

- [x] Add `not_required` translation in `static/app.js` coverage detail view, without changing underlying statuses.
- [x] Add narrow static test if needed; run JavaScript syntax check and relevant browser regressions.

## Task 3: Verification and delivery

- [x] Run S2/S4 and authorization tests, CI, full QA if feasible; enumerate SKIP and BLOCKED separately.
- [ ] Update current release state and report. Verify source ZIP and Git history before delivery.
