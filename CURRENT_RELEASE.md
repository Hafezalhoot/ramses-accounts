# Ramses Accounts — Current Development Release

- Version: `V8.1E-G2P` — 31 October 2026
- Baseline: G2O; previous sources, audits and schema migrations preserved.
- Status: **DEVELOPMENT / TEST ONLY — NO GO for real patient data or cash**.
- Scope: preflight, request, two-person approval, final financial close and zero-charge cancellation for inpatient, NICU and operation cases; no clinical discharge.
- Integrity: SQLite transactional approval, idempotent request, historical audit snapshot and closed-case DB mutation guards.
- Tests: 76 scripts — **72 PASS, 3 SKIP due historical fixtures, 1 BLOCKED (V8.0 ZIP absent)**; synthetic Chromium UI at 1440/375/320.
- Read: `RAMSES_V81E_G2P_CASE_CLEARANCE_QA_AR.md`, `QA_G2P_TEST_RESULTS.tsv`, `RAMSES_MASTER_PLAN_AR.md`.
- Not delivered: bed occupancy / per-day pricing, operation/NICU resource charging, complete inventory/suppliers/physician payables, full RBAC, clinical discharge integration, historical migration verification, real hospital rollout or accountant sign-off.

To reproduce the blocked test, place the genuine V8.0 archive in `tests/fixtures/` or use the `RAMSES_V80_ARCHIVE` environment variable. Never use a fake source ZIP.
