# S2 Cashier Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Verify a full cashier day and make the existing cash-to-treasury path safe and accessible.

**Architecture:** Keep current FastAPI/SQLite voucher and shift posting. Add one synthetic financial-day test and narrow retry protection in the existing voucher keys table. Show treasury deposit action in existing shifts UI, not a new management page.

**Tech Stack:** Python 3.13, FastAPI/TestClient, SQLite, vanilla JavaScript, Playwright Chromium.

**Spec:** `docs/project-autopilot/S2_CASHIER_ACCEPTANCE_SPEC.md`

## Global Constraints

- TEST_ONLY; do not push, change production, add new dependencies, or store real financial or patient data.
- Keep independent shift approvals and previously immutable journals.
- No retroactive periods or doubled external receipt/revenue.

## Review Focus

- Partial deposit network replay: exact same retry key cannot book another voucher.
- Reused key with a different amount/source must fail rather than return wrong receipt.
- Non-receiver cannot move funds to internal treasury.
- External next shift must not inherit money already delivered.
- UI should only offer physical deposit to a receiver with an open central shift.

### Task 1 - Financial-day acceptance test

**Files:** Create `tests/test_s2_cashier_24h_acceptance.py`.

- [x] Write and run synthetic day scenario covering 3 external shifts, 1 internal, independent receiver, daily report and GL.
- [x] Identify any verified blockers, fix in a separate task.

### Task 2 - Retry-proof treasury deposit

**Files:** Modify `cashier_api.py`. Test `tests/test_s2_treasury_retry.py`.

- [x] Write a failing duplicate-partial-deposit idempotency scenario (same key, identical/mismatched body, concurrent semantics).
- [x] Protect retry with the existing `voucher_request_keys` table in the same transaction.
- [x] Re-run the test and existing treasury/shift scenarios.

### Task 3 - Browser-accessible treasury receipt

**Files:** Modify `static/app.js`; create `tests/browser_s2_cashier_treasury_ui.py`.

- [x] Add failing browser test for in-screen treasury action and data wiring.
- [x] Implement smallest action with amount, note, stable retry key; prevent invalid receiver from seeing action.
- [x] Re-run browser tests at 375px and 1440px with RTL and no page errors.

### Task 4 - Evidence and packaging

**Files:** Update `docs/project-autopilot/PROJECT_STATUS.md`, `TEST_REPORT.md`.

- [x] Run subset and full source smoke/CI; explicitly distinguish TestClient and browser offline checks from network deployment.
- [x] Commit changes to isolated S2 branch, package source + test report + git history bundle, verify hashes.
