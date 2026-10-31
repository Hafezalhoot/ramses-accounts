# Ramses V8.1E-P0 - shift coverage QA (TEST ONLY)

Date: 2026-10-30. Based on the V8.1C-QA1 full source with approved V8.1D RBAC planning retained. No changes to patient payment posting, financial ledger, shift handovers, cash balances or production deployments.

## Implemented now

- New independent read-only module `shift_coverage.py` and authenticated endpoint `/api/shifts/coverage?month=YYYY-MM`.
- 3 expected shift slots for each monitored, active, mapped cashier point/day; per-point monitored range inferred from earliest registered shift, prior history labelled unknown.
- Distinct conditions: not monitored, upcoming, running/grace, missing electronic record, open past shift end, cashier count submitted, reviewed and closed.
- The standard Shifts screen now shows a responsive coverage matrix with point, day, shift and status filters, separate from actual shift sessions.
- Dashboard now displays a scoped missing/overdue/review alert, with a link to the Shifts view.
- Existing hospital cashier daily summary includes coverage status, `shift_coverage_complete`, `is_provisional` and `financially_certified=false` (full financial certification is not available).
- `/api/shifts/coverage` is restricted to owner/reviewer or assigned station clerk. No physical count/expected cash is returned to clerks.
- Test-only ZIP includes existing finance code, V8.1D RBAC roadmap, V8.1E design and new automated tests.

## Tests executed

- New independent Python/API: `tests/test_shift_coverage_v81e_p0.py` PASS (missing evening, morning awaiting review, owner daily provisional, clerk scope, not-monitored old history, no ledger mutation).
- New isolated Chromium: `tests/browser_shift_coverage_offline.py` PASS (missing status, dashboard alert, point/shift/status filtering, responsive mobile layout, no page JS errors).
- Existing high-risk finance/shift tests, including credit notes, invoice collections, shift handoff and cash posting guard, PASS.
- Previously existing 29 available independent Python test files PASS in separate test batches; new P0 Python test PASS, for a total of **30 passing files**.
- One historical file `tests/test_billing_upgrade_v81.py` cannot pass because an original V8.0 source package is not included. It is a missing test fixture/source prerequisite, not a verified migration failure.
- All seven simulated offline Chromium scripts PASS including the new shift-coverage screen. One separate `test_free_preview_e2e.py` live localhost preview HTTP test also passed after its isolated source-copy fixture was updated to include the new module.
- Full end-to-end browser against production-like concurrent cashier HTTP sessions, pen test and real restore/off-device backups remain untested; this is still a demo package.

## Important limitations / why this is NOT a complete V8.1E

1. No owner-defined active monitoring start / operating calendar yet. P0 infers monitoring start from the first recorded shift for each point. Never claim an earlier date is complete or empty.
2. Historical missing slot times use current shift starts; effective-dated schedule versions and frozen expected-slot snapshots are P1.
3. No owner-approved non-working slot override and no duplicate-safe persisted in-app notification task queue yet. Visible alerts are from live dashboard queries.
4. No late paper packet, mixed summary/detail patient registration, numbered sealed envelopes or custody transfer workflow implemented yet.
5. No bank-clearing or cash reallocation logic for old funds, no late GL posting and no financial hospital-day certification.
6. Role templates / per-page authorizations (V8.1D) are documented but not implemented.

Full design: `SHIFT_FIRST_DAILY_MONITORING_PLAN_V81E.md` and `RAMSES_MASTER_PLAN_AR.md` (M3.6).
