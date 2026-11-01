# G3K supplier payment voucher linkage implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Each task uses RED → GREEN → review.

**Goal:** Connect a G3J authorization to an independently approved bank voucher without duplicate supplier liability or false bank-confirmation claims.

**Architecture:** Reuse existing vouchers, fund_movements, GL 2200, bank_statement_matches; add a unique immutable supplier payment–voucher link and guarded protected category. Expose read-only provenance report. No direct transfer execution.

**Tech Stack:** FastAPI, SQLite, existing vanilla RTL JS/Cairo, Chromium.

**Spec:** docs/superpowers/specs/2026-11-01-g3k-supplier-ap-bank-link.md

**Global constraints:** TEST ONLY, no production data, no automated bank transfers; preserve accounting and historical migrations; encrypted backup before DDL; no new packages.

**Review Focus:** double payment; bypass generic category; forged approval through SQLite; bank confirmation without signed statement; voided matches/reversals; disabled vendor; CSRF and role scope.

- [x] Write failing end-to-end synthetic tests for voucher creation, review, Dr2200/Cr bank, no double posting, rejection, and bank reconciliation status.
- [x] Add schema link immutability and SQL guard, seed protected voucher category, add ledger mapping, and special API creation under existing bank and inventory grants.
- [x] Protect generic voucher creation and reversal; reporting distinguishes booked vs matched vs signed statement and outstanding.
- [x] Test G3J→G3K encrypted upgrade from frozen source, and UI on 320/375/1440 with Cairo fallback.
- [x] Full regression, CI, Git bundle, ZIP manifest, independent extraction, Library persistence, document outstanding NO-GO gates.
