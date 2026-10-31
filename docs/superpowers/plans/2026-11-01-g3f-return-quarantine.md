# G3F Return Quarantine Implementation Plan

> **For agentic workers:** Use executing-plans. Deliver a locally verified, nonproduction source package.

**Goal:** Prevent returned FIFO items from being issued until a qualified, independent clinician clears the exact returned lot.

**Architecture:** Append-only per-return-line inspection records; existing return/GL remain unchanged; FIFO and SQLite guards count released returns only. Existing clinician identity/grant reused; clinical UI adds a separate inspection queue.

**Tech Stack:** Python FastAPI, SQLite, Vanilla JS, unittest-style integration scripts.

**Spec:** `docs/superpowers/specs/2026-11-01-g3f-return-quarantine-design.md`

## Global Constraints
- No real or production database, no secrets in artifacts, no claim of verified clinical reusability.
- Fail closed on uninspected G3D returns and continue to show existing financial on-hand and GL correctly.

## Review Focus
- Existing G3E approved returns without inspections must remain non-allocatable.
- SQLite direct inserts must not bypass clinical release checks.
- Revocation of clinical grant/identity must apply before inspection writes.
- Quarantine must not incorrectly reduce GL/case return value.
- A previously released lot with later consumption cannot be silently reclassified.

### Task 1 — Failing API integration test
- [ ] Add `tests/test_v82_g3f_return_quarantine.py` exercising return approval -> allocation refusal -> clinician release -> allocation success, negative decisions, revocation, direct SQL and reconciliation.
- [ ] Run test and inspect expected RED.

### Task 2 — Schema + server
- [ ] Add immutable inspection ledger and SQL review/lot-allocation guards in `schema.sql`, with pre-DDL encrypted backup trigger replacement in `bootstrap.py`.
- [ ] Implement authenticated inspection queue/decision and stock availability metrics in `inventory.py`; whitelist only those clinical routes in `app.py`.
- [ ] Run new test GREEN and existing G3D regression; adapt existing reissue test to require explicit inspection.

### Task 3 — UI and QA
- [ ] Show available/quarantine in inventory UI and a minimal medical inspection panel in `static/app.js`; safe Arabic labels.
- [ ] Add G3F test to `scripts/ci_smoke.py` and G3F regression of date/role/replay/immutable SQL.
- [ ] Run full suite, syntax, a local UI/browser smoke where feasible, migration and archive/restore gate; record output unambiguously.

### Task 4 — Delivery
- [ ] Update `README_G3F_AR.md`, release state, risk tracker and QA record with exact observed results.
- [ ] Package ZIP + Git Bundle with hashes, extract and verify, link verified output. No deploy.
