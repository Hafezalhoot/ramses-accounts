# S4 Integrated Day Implementation Plan

> For agentic workers: execute task-by-task with test-first checks and independent review.

**Goal:** Prove an interdependent single-DB financial day with explicit source-to-ledger reconciliation rather than multiplying UI screens.

**Architecture:** Reuse current FastAPI routes and existing financial tables. Create one isolated synthetic SQLite DB and role-specific API sessions; do not adjust financial behavior to fit tests. Add only test/report code unless a real regression fails.

**Tech Stack:** Python 3, FastAPI TestClient, SQLite, legacy source-owned tests, optional Uvicorn HTTP bridge.

**Spec:** `docs/project-autopilot/S4_INTEGRATED_DAY_SPEC.md`.

## Global Constraints
- Development-only, synthetic records and no externally posted payments.
- No production clock bypass, live role mutation, cash movement or migrations.
- Preserve S1-S3 regressions and original V8.0 blocker.

## Review Focus
- Cash receipts from patient invoice must not double-book generic cash revenue.
- Central transfer must net physical source cash to zero with exactly one transfer per source.
- Supplier 2200 and bank voucher must be independently attributed, not only equal in total.
- Prior closed period must not be rewritten by historical envelope correction.
- A calendar/schedule gap must block close; unapproved bank statements must block close.

### Task 1 - Integrated synthetic cash and patient day
**Files:** create `tests/test_s4_integrated_day.py`.
- [x] Write test using existing routes for 3 shifts and actual patient invoice collection.
- [x] Run test, observe failure at missing setup or real defect, repair test setup only as needed.
- [x] Verify GL, physical fund balances, cash journals and independent reviews.

### Task 2 - Supplier bank and control account in same DB
**Files:** extend `tests/test_s4_integrated_day.py`.
- [x] Approve PO, goods receipt, invoice match and due schedule.
- [x] Enforce independent payment request, bank voucher and statement confirmation.
- [x] Compare source-attributed vendor 2200 report and GL with bank movement.

### Task 3 - Historical recovery and close controls
**Files:** extend same test, and project status docs.
- [x] Exercise legitimate blocked preflight before prerequisite satisfaction.
- [x] Resolve historical paperwork without backdated cash or altered original period.
- [x] Test and describe exact month-close status, don't claim real UAT.

### Task 4 - Regression, evidence and package
**Files:** reports under `docs/project-autopilot`, release README, source ZIP and bundle.
- [x] Re-run focused acceptance and CI, investigate failing regressions.
- [x] Write observed release gate status, hash delivered artifacts, extract and check ZIP.
- [x] Commit isolated branch; do not publish or deploy to hospital.

## Observed execution / gate interpretation

Completed test-only implementation and independent script runs (see `docs/project-autopilot/TEST_REPORT.md`). One intermittent 500 seen during unrelated parallel-suite load was NOT root-caused; three subsequent standalone real HTTP repeats passed. The production-release gates remain explicitly blocked, so checked implementation tasks do **not** assert hospital UAT completion.
