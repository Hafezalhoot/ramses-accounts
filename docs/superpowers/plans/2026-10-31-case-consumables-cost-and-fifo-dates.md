# G3C Patient Consumables Cost Implementation Plan

> **For agentic workers:** Execute task-by-task with `test-driven-development` and `verification-before-completion`, on isolated `feat/g3c-case-consumables-cost` source. Do not deploy.

**Goal:** Make the existing posted FIFO consumable costs auditable per patient case while preventing retroactive FIFO valuation drift.

**Architecture:** Reuse inventory issues, line allocations, GL and point-level authorization without schema tables or new postings. Add two SQL triggers with encrypted pre-DDL backup for older databases. Provide a read-only report UI in the inventory screen.

**Tech Stack:** Python, FastAPI, SQLite triggers, vanilla JavaScript, Chromium.

**Spec:** `docs/superpowers/specs/2026-10-31-case-consumables-cost-and-fifo-dates.md`

## Global constraints
- No actual patient data or live deployment, no new GL posting pathways.
- Existing backdated approved history remains untouched; only reject NEW out-of-order approvals.
- Independent prepare/review and current grants enforced on read and write.

## Task 1 — Read-only per-case cost
- [ ] Test real two-lot FIFO case consumption, unlinked/pending exclusions, unauthorized point/grant, revocation and 404.
- [ ] Confirm RED on original G3B; implement single endpoint under inventory router.
- [ ] Confirm GREEN; rerun G2T inventory tests.

## Task 2 — Chronological FIFO approval guard
- [ ] Test later-approved issue followed by backdated issue and backdated receipt, direct SQL attempts, no partial side effects; confirm RED.
- [ ] Add minimal API checks under existing approval transactions and immutable SQL triggers.
- [ ] Confirm GREEN; verify full bootstrap G3B encrypted migration/restore.

## Task 3 — Inventory page and release validation
- [ ] Test a case-cost query in Chromium (desktop/mobile) with success/rejection/clear-previous-data.
- [ ] Add narrow responsive section in `static/inventory_ui.js` and synchronize test-only version labels.
- [ ] Full suite + CI, source lint, independent extracted ZIP digest and smoke tests, Git bundle, state docs.
