# G3J Cairo + Payment Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Track RED/GREEN gates.

**Goal:** Ship a verified source-only development increment with Cairo typography and safe preliminary supplier payment instructions.

**Architecture:** Additive inventory-linked SQLite tables, secure FastAPI operations and one RTL inventory panel; no change to approved GRN or cashbook. Google Fonts CSS2 is whitelisted only for styles/fonts, with local system fallback; no font binaries bundled.

**Tech Stack:** FastAPI, SQLite, Vanilla JS, CSS, Chromium.

**Spec:** docs/superpowers/specs/2026-11-01-g3j-cairo-payment-requests.md

## Global Constraints
- All changes local TEST ONLY; no live data, no payouts, no approval for deployment.
- Preserve audited G3I SQL and transaction immutability; future changes require new documents.
- No font files in deliverables; Cairo loading may be online or locally installed only.

## Review Focus
- A stale reviewer after grant revocation must be denied.
- Two requests must not exceed installment amount even with direct SQLite insert.
- Invoice/receipt/schedule author cannot review their own source payment request.
- Rejected requests release capacity, but approved remain immutable.
- Font hierarchy works at 320px and printing; external-font CSP is strictly scoped.

## Tasks
- [ ] Create typography and API regression tests, observe RED.
- [ ] Update HTML/CSS and narrowly scoped CSP; observe GREEN.
- [ ] Add payment requests schema, API and SQL guards with RED/GREEN tests.
- [ ] Add explicit non-paying reviewer UI, test browser and responsiveness.
- [ ] Run original CI and full regression, independent browser smoke and upgrade.
- [ ] Commit, produce ZIP + Git bundle + SHA-256 report, verify from extracted files.
