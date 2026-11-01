# G3M Supplier Journal Attribution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use executing-plans and test-driven-development in this session.

**Goal:** Establish a source-evidenced, maker/checker mapping of unattributed AP control lines without touching posted monetary entries.

**Architecture:** Immutable `supplier_journal_attributions` documents under SQLite guards; FastAPI inventory routes for propose/review/list; G3L source subledger consumes approved mappings as-of review date; existing RTL inventory panel displays proposals and safe approvals.

**Tech Stack:** Python FastAPI, SQLite, vanilla JavaScript/CSS, Playwright/Chromium.

**Spec:** `docs/superpowers/specs/2026-11-01-g3m-supplier-attribution.md`

## Global Constraints
- No production/actual money movement. No auto backfill. Historical V8.0 archive still unavailable.
- Owner and authorized staff with current grants only; checker must have reviewer role or be owner and independent of source journal and maker.
- Preserve G3L source mapping, failed date and unauthorized paths must not leak/mutate data.

## Review Focus
- A source journal with a different document FK must never be reattributed.
- Two proposals for the same journal must not be simultaneously active.
- Direct SQLite must not forge review, change evidence or delete documents.
- Historical report must not show a mapping approved after requested as-of date.
- Released ZIP must match source Git and run extracted tests and browser.

## Tasks
- [x] Write API/GL regression script, observe RED missing route.
- [x] Add schema and API, observe GREEN and direct SQL denial.
- [x] Attach approved mappings to G3L control report without modifying GL and verify historical as-of.
- [x] Write browser script RED then implement Arabic RTL maker/checker UI with signed amount and proof.
- [x] Freeze authentic G3L schema, test additive upgrade and encrypted restore.
- [x] Run CI, full regression, Chromium, compile/syntax checks, inspect & package release.
- [x] Commit clean Git, produce and verify ZIP + Git bundle with checksums, findings and docs.
