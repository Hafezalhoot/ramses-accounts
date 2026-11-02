# Ramses S1 Operational Stabilization Plan

> **For agentic workers:** Implement inline using the existing repo, one tested slice at a time. No production or patient-data access.

**Goal:** Replace the 23-panel inventory mega-view with task-specific navigation without removing any existing capability, and provide one real browser-to-application-to-SQLite acceptance journey (or transparently document the browser environment limitation).

**Architecture:** Preserve the current FastAPI + SQLite backend, permissions and existing inventory event handlers. Partition the existing HTML string into six exclusive task areas; share a small keyboard-accessible task selector and a pending-action summary. Test the UI with Chromium using realistic role fixtures. Separately exercise a synthetic independent clerk/reviewer inventory journey through real FastAPI handlers/SQLite using an actual browser transport where feasible.

**Tech:** Vanilla HTML/CSS/JS, Python 3.13, FastAPI TestClient, local Chromium/Playwright.

**Spec:** This file; derived from `RAMSES_G3N_INDEPENDENT_OPERATIONAL_AUDIT_2026-11-02.md` and user approval to prioritize stabilization rather than new pages.

## Global constraints
- Keep the V8.1E-G3N data model, permission checks, GL postings, server routes and Cairo typography intact.
- No direct live hospital, external bank, or patient data; synthetic and disposable fixtures only.
- Do not claim production readiness; historical V8.0 upgrade/off-site backup/UAT remain blocked.
- No new supplier feature/module or fictional accounting posting.

## Testable tasks
1. **RED:** Chromium test expects six accessible focus areas, only active area exposed, visible task counters/shortcuts, role-sensitive forms and navigation. Verify failure on baseline.
2. **GREEN:** Add minimal grouped HTML and task selector to `static/inventory_ui.js`; style focus, mobile stacking, and hidden areas in `static/styles.css`. Re-run test and targeted historic browser scripts; fix regression without weakening test intent.
3. **Integration proof:** Try real Chromium + disposable Uvicorn. If browser loopback is blocked, build a documented browser request bridge into the *actual* FastAPI app+SQLite (not mocked business API), and assert original source events change journal/stock correctly under independent identities; test success and forbidden paths.
4. **Quality gates:** fresh existing `scripts/ci_smoke.py` and `scripts/qa_g2t_full.py`, all pertinent historical offline browser tests, Python/JS lint or syntax checks, inspect git diff and package ZIP + Git history and verify from clean extraction.
5. **Handoff:** Document measured before/after viewport lengths, acceptance coverage labels (`browser mock`, `browser↔ASGI↔SQLite`, `browser HTTP`), remaining risks, and exact next stage in project state.

## Review focus
- Keyboard and RTL focus order; 44px mobile tap targets; hidden forms not submitted accidentally.
- Owner, clerk, reviewer all see only their authorized capabilities; no client-side pseudo-security substituted for API grants.
- After creating or reviewing a document, selected work area stays selected across server refresh.
- Pending counts include returned/rejected documents only if they are actually pending (no mislabeling).
- Real browser failure due to infrastructure must be reported, not silently converted into mocked coverage.
