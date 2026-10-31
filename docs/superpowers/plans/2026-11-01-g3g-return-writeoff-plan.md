# G3G Rejected Return Writeoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use test-driven-development and executing-plans task by task; no production deployments.

**Goal:** A financially and physically traceable, independently approved disposal of medically rejected consumable returns.

**Architecture:** Extend the source-driven SQLite/FastAPI inventory subledger, preserve legacy immutable returns, and add a single original-lot linked writeoff document. Add a dedicated GL expense account (5195). Provide RTL warehouse controls via the existing inventory page.

**Tech Stack:** Python 3, FastAPI, SQLite, vanilla JavaScript, standalone Python test runners, Chromium.

**Spec:** `docs/superpowers/specs/2026-11-01-g3g-return-writeoff-design.md`

## Global constraints
Test only; synthetic patient/stock identities. No live database, no migration against production, no non-consensual account actions. Maintain FIFO/medical quarantine and original return accounting.

## Review focus
1. Pending/rejected/approved partial writeoffs: only approved subtract from stock and ledger.
2. Multiple requests and direct SQLite tampering cannot over-writeoff the same lot line.
3. Historical unverified G3E reissues are not silently disposed without physical audit.
4. Grant revocation, self-approval, and sealed month all fail closed.
5. UI shows loss and review without exposing patient data; upgrade creates recoverable encrypted rollback.

### Task 1 — Defining accounting invariants
**Files:** `tests/test_v82_g3g_return_writeoffs.py`, `schema.sql`, `inventory.py`, `ledger.py`.
**Interfaces:** POST `/api/inventory/writeoffs`, POST `/api/inventory/writeoffs/{id}/decision`, GET `/api/inventory/writeoffs/queue`.
- [ ] Write failing HTTP test for medically rejected return, partial writeoff and exact GL.
- [ ] Run test; verify expected feature absence, not broken fixture.
- [ ] Implement minimal schema, signed journal, API and source-based stock reconciliation.
- [ ] Re-run test, enforce immutability, authority and accounting conservation.

### Task 2 — Backward-compatible upgrade + UI
**Files:** `tests/test_v82_g3g_upgrade.py`, `static/inventory_ui.js`, `tests/browser_g3g_writeoff_ui_offline.py`.
- [ ] First write regression for G3F migration, negative medical approval and retained return journal.
- [ ] Verify regression fails for G3G absence, then pass after migration and UI implementation.
- [ ] Test mobile/desktop Arabic transaction flow and no extra patient identifiers.

### Task 3 — Evidence and artifact
**Files:** `README_G3G_AR.md`, `RAMSES_V81E_G3G_WRITEOFF_QA_AR.md`, `CURRENT_RELEASE.md`, `PROJECT_AUTOPILOT_STATE_AR.md`, `scripts/ci_smoke.py` and release labels.
- [ ] Include focused suite in CI, run all regression tests and report PASS/SKIP/BLOCKED separately.
- [ ] Validate Python/JS/SQL/launcher, source manifest and local Git history.
- [ ] Build ZIP and history bundle, extract and test, verify hashes, save report; never deploy.
