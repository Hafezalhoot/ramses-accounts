# S15 Fee Liability Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. Steps use checkboxes to track tests.

**Goal:** Add a read-only and owner-scoped GL 2320 reconciliation gate before designing service-fee payouts.

**Architecture:** Pure SQLite financial control function in `service_fee_reconciliation.py`, exposed via the existing `service_fees.router` without a schema or payment change. Synthetic unit tests plus an extended existing S14 TestClient acceptance.

**Tech Stack:** Python 3.13, SQLite, FastAPI, existing project tests.

**Spec:** `docs/project-autopilot/S15_FEE_LIABILITY_RECONCILIATION_AR.md`

## Global constraints

- TEST ONLY; no external payment, ledger mutation, schema rewrite, or production deploy.
- Read-only evidence, owner-only server API, all amounts integer piasters; preserve original S14 history.
- No unverified claims of full regression passing. CI on GitHub Actions is currently disabled.

## Tasks

- [x] RED: isolated SQLite unit test fails before helper exists.
- [x] GREEN: implement GL vs approval/reversal checks and rerun.
- [x] RED: add multiple GL 2320 lines within one decision journal and observe failure.
- [x] GREEN: require exactly one linked 2320 line per journal and rerun.
- [ ] Integrate owner-scoped GET into existing S14 router; extend S14 TestClient regression.
- [ ] Add the isolated unit test to `scripts/ci_smoke.py` on an S15 branch.
- [ ] Independent review and rerun S14 TestClient, local CI and full QA from exact GitHub checkout, record evidence.
- [ ] Keep PR unmerged until review; do not implement payment or cash movements as part of this read-only slice.
