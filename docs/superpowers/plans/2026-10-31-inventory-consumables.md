# G2T Central Consumables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add safely journaled, independently approved consumables receipts and issues to Ramses Accounts.

**Architecture:** One module with router and reconciliation helpers; new additive SQLite schema and existing manual-journal source linking; simple owner-facing RTL screen. Monetary storage is integer piasters; physical stock is derived only from immutable documents.

**Tech Stack:** FastAPI, Python stdlib SQLite, vanilla JavaScript, existing TestClient.

**Spec:** `docs/superpowers/specs/2026-10-31-inventory-consumables-design.md`.

## Global constraints
- No actual patient identifiers or real cash in tests or package.
- Keep patient billing, shift and banking untouched.
- No automatic cash movement for supplier invoices.
- Protect closed month, concurrency, idempotency and history.

## Review focus
- Race of two approvals over last units; only one must succeed.
- Duplicate supplier invoice submitted with different request keys.
- Expired lot or receipt from future date must not be issued.
- Case closed or unassigned caller must not gain access.
- A forged manual journal reversal must not touch approved stock documents.

## Task 1: Transactional procurement and FIFO cost posting
**Files:** Create `inventory.py`; modify `schema.sql`, `app.py`; test `tests/test_v82_g2t_inventory.py`.
**Interface:** inventory router `/api/inventory`, stock reconciliation `inventory_reconciliation(c, period)`.
- [ ] Write and execute failing test for expected API and GL postings.
- [ ] Add additive schema and SQL immutable/quantity triggers.
- [ ] Implement role grants, vendor/item catalog, receipt maker/checker, issue maker/checker and FIFO allocations.
- [ ] Verify new tests, existing ledger and billing tests.

## Task 2: Reconciliation and period gate
**Files:** Modify `app.py`; tests `tests/test_v82_g2t_inventory.py`.
- [ ] Fail test for pending inventory docs or wrong linked journal on monthly preflight.
- [ ] Add period close preflight and linked journal reconciliation.
- [ ] Verify with synthetic data, direct SQLite attempted mutations and regression.

## Task 3: UI + historical schema upgrade + handoff
**Files:** `static/inventory_ui.js`, `static/index.html`, `static/app.js`, `static/styles.css`, `tests/test_v82_g2t_upgrade.py`, docs.
- [ ] Add owner/reviewer/clerk screen with permission-aware state and explicit error/loading states.
- [ ] Test minimal interactive/mobile route and JS syntax.
- [ ] Preserve G2S actual DDL fixture; initialize twice, check old data intact.
- [ ] Run full test suite; package ZIP and verify unpacked file hashes; record all blocked historical tests.
