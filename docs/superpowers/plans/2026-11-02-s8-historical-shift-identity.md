# S8 Historical Shift Identity Implementation Plan

> **For agentic workers:** Use the existing project TDD and verification skills; this plan executes inline on isolated local source.

**Goal:** Stop historical cashier names changing visually after future schedule changes.

**Architecture:** Derive display names at the existing effective-dated `cashier_ops` module seam; return them alongside immutable shift codes. Consume them in the existing RTL screen, without schema or accounting policy changes.

**Tech Stack:** Python/FastAPI/SQLite, vanilla JS, Playwright/Chromium, existing source-owned QA runner.

**Spec:** `docs/project-autopilot/S8_HISTORICAL_SHIFT_LABEL_SPEC.md`

## Constraints
- No schema migration or production writes; no new dependencies.
- Keep server-side permissions, existing amount calculation and fallback for legacy sessions.
- All test data synthetic.

## Review focus
- Old custom slot renamed with future effective date must retain the old display name.
- Unknown legacy shift code must render nonblank escaped code.
- Restricted reviewer cannot see shifts without grant.
- No additional ledger/movement/audit entries on report read.
- Arabic/RTL desktop and 375px mobile show consistent labels.

## Task 1: API shift-name regression
- [x] Add `tests/test_s8_historical_shift_identity.py` exercising new station, today shift, future rename, both API endpoints, old records and no financial mutation.
- [x] Run before implementation and observe failure for missing/incorrect historical shift name.
- [x] Add minimal helper at `cashier_ops` seam and wire `app.py` response fields (no policy change).
- [x] Rerun test and related shifts suites.

## Task 2: Browser regression
- [x] Add offline Chromium test for latest plan vs older row and day modal, 1280 and 375 widths.
- [x] Observe pre-change failure, then update existing `static/app.js` to use server-provided label and safe fallback.
- [x] Rerun browser test and JS syntax.

## Task 3: Release verification
- [x] Run CI smoke and complete source QA when time permits, preserve all blocked/skipped categories.
- [x] Inspect diff / relevant permissions, update project continuity.
- [x] Commit isolated S8 and build/verify ZIP and Git bundle; never promote to hospital production.
