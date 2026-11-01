# G3N supplier opening statement verification — implementation plan

> For agentic workers: use the current session's executing-plans and TDD skills task-by-task.

**Goal:** Record external supplier balance confirmations against prior closed-month-end GL 2200 amounts, independently reviewed, without creating or editing any journal, cash voucher, or invented historical opening balance.

**Architecture:** SQLite document and immutable audit triggers; a source fingerprint captures the 2200 journal set and supplier-attribution state at a previous month-end. FastAPI proposal/decision endpoints reuse inventory grants and idempotency. An RTL panel shows statement vs GL amounts, reconciliation limitations, and reviewer actions. Frozen G3M upgrade + encrypted restore and independent browser/API regressions.

**Tech Stack:** FastAPI, SQLite, plain JS HTML/CSS, synthetic TestClient, existing Chromium harness.

**Spec:** existing `RAMSES_G3M_FINDINGS_TRACKER.json` and `README_G3M_AR.md`, plus the design decisions herein.

## Global constraints
- Test-only, NO-GO for real hospital operations.
- No GL journal, cash, bank, VAT or historical changes.
- No invented supplier balances; external statement value provided explicitly.
- Prior month-end cutoff, positive or zero EGP balances only; supplier debit balances are exceptions.
- Pending and approved uniqueness per vendor/cutoff; rejected can be replaced without deletion.
- SQL and API maker-checker, active grant validation, immutable evidence, stale detection, replay safety.
- Approval requires total 2200 source reconciliation and equality between external statement and vendor GL balance, with sources unchanged from creation.
- Approval is evidence review for synthetic control, not proof external authenticity or the bank beneficiary.

## Review focus
1. Ledger changes after proposal but before approval must block approval and require new document.
2. Unattributed journals (including zero net) must block approval, not be silently absorbed.
3. User with revoked reviewer grant, or original proposer, must never approve even by SQL.
4. Past month-end frozen data must not incorporate new information by retroactive attribution unless explicitly reviewed.
5. Zero and negative vendor accounts cannot be implicitly treated as vendor payments.

## Tasks
- [x] Add focused failing `tests/test_v82_g3n_supplier_opening.py` covering missing API, mismatch, stale, replay, no posting, SQL approval and negative cases.
- [x] Add additive document schema + SQL guards, and FastAPI endpoints with complete digest verification, then rerun focused test.
- [x] Add supplier opening balance panel and review UX, and browser test for responsive RTL.
- [x] Freeze G3M source schema, test additive migration and encrypted rollback restore; register CI tests.
- [x] Run full QA (132/138 pass; 5 skip, 1 V8.0 blocked), CI (66/66), browsers (12/12); versioned Git/ZIP extraction documented separately in release verification.

**Ruling:** Opening balances are CONTROL SNAPSHOTS only, never booked balances; accounting entries need separately approved financial policy and source documents.
