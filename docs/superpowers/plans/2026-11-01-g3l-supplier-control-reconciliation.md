# G3L Supplier Control-Account Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make account 2200 differences and supplier-specific GRN/payment/reversal sources auditable without fictitious adjustments.

**Architecture:** Read-only source-matched GL projection in a separate module, exposed with existing inventory permissions and summarized on the Cairo RTL inventory view. Source journal IDs are immutable; account 2200 is the control truth.

**Tech Stack:** Python 3/FastAPI, SQLite, vanilla JS/CSS/Chromium.

**Spec:** `docs/superpowers/specs/2026-11-01-g3l-supplier-control-reconciliation.md`

## Global Constraints
- No actual payment execution, VAT or inferred credit/debit note GL entries.
- No production schema modification or finance data alteration.
- As-of reporting uses posted journals by journal date, including reversals.
- Never claim that zero unexplained GL entries certifies all historical vendor balances.

## Review Focus
- Reversed voucher with past as-of must count as paid before reversal date.
- Approved GRN without an approved supplier invoice is still a posted 2200 obligation.
- Unattributed manual/legacy 2200 posted journal must be flagged, not allocated to a vendor.
- Missing, duplicated, mismatched or unposted source journal must flag a mismatch.
- Without inventory grant, per-vendor identities must not leak.

### Task 1 — GL provenance projection
- [ ] Write failing API integration test in actual synthetic G3K flow.
- [ ] Run and verify expected fail.
- [ ] Build supplier ledger report module using DB journal entries, not invoice totals.
- [ ] Pass authorized, unauthorized, partial, reversal and unexplained GL tests.

### Task 2 — Operator UI
- [ ] Write failing Chromium test for as-of report with Cairo layout.
- [ ] Render supplier 2200 audit summary + per-vendor balances + discrepancy state.
- [ ] Verify at 320, 375, 1440, no horizontal overflow, no JS errors.

### Task 3 — Release verification
- [ ] Update app labels, tests, operational docs and project state, preserve historical G3K.
- [ ] Run focused tests, comprehensive regression and CI, review failures accurately.
- [ ] Commit only verified source; ZIP and Git bundle, independent extraction/hash/test.
- [ ] Save artifacts in Library and report TEST_ONLY NO-GO limitations.
