# G3D Inventory Returns Implementation Plan

> Implement in isolated branch using TDD; no live hospital data or deployment.

**Goal:** Traceable non-drug returns from original approved FIFO issue, with atomic stock/GL and correct case cost.
**Architecture:** One immutable return header + allocation-linked lines; use existing inventory permission, billing case scope, ledger_post, month_open, idempotency. Return accounting from original lot unit price.
**Tech Stack:** FastAPI/Pydantic, SQLite triggers, vanilla JS frontend, existing script tests.
**Spec:** `docs/superpowers/specs/2026-11-01-inventory-returns-design.md`

## Tasks
- [x] T1 API negative-and-positive integration test first, then minimal tables/triggers/handlers, stock/FIFO/reconciliation updates. Commit.
- [x] T2 Case cost and UI controls test-first, then transparent net versus gross issued/returned; prevent stale data exposure. Commit.
- [x] T3 Frozen G3C upgrade fail-closed and encrypted restore test, add CI gate, run full regression. Commit.
- [ ] T4 Report, manifest, clean ZIP, isolated extracted verification and Git history bundle. No deploy.

## Risk and review focus
- Capacity after repeated partial returns and concurrent requests
- Wrong lot cost and FIFO order around returned stock
- Reversal of source journal after return posted
- Backdated/closed month and already-closed patient case
- Replayed request after grant revocation

- G3D additional TDD gate: pending return prevents case clearance preflight and direct SQLite case status change.
