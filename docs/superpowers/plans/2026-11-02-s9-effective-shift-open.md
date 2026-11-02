# Effective-dated Shift Opening Implementation Plan

> For agentic workers: execute this plan directly with mandatory test-first RED/GREEN and fresh regression evidence.

**Goal:** prevent a cashier from being offered a shift code invalid for the selected fund and Cairo business date.

**Architecture:** use the already authoritative effective-dated schedule (`cashier_ops.slots_for`) behind a read-only authenticated endpoint. Both opening dialogs share one asynchronous date/fund picker with stale-request suppression. The existing write transaction remains untouched.

**Tech Stack:** FastAPI, SQLite, vanilla JavaScript RTL, TestClient and Chromium.

**Spec:** `docs/project-autopilot/S9_EFFECTIVE_SHIFT_OPEN_SPEC.md`

## Global Constraints
- Test only, synthetic disposable databases, no production mutation/deploy.
- No schema or financial posting changes; server role checks cannot be weakened.
- Preserve S8 historical shift labels and Cairo font.

## Review Focus
- Future schedule is stored but not in force today: ensure today's code stays selectable.
- A different fund uses a different schedule: ensure fund change invalidates old options.
- Unauthorized/disabled operating day: no selectable codes or data leakage.
- Rapid date changes: stale responses must not overwrite current options.
- Empty/error response: prevent submission; previous form disabled state must not leak to subsequent modals.

### Task 1: Date/fund-specific read-only options

**Files:** Modify `app.py`; create `tests/test_s9_shift_open_options.py`.

**Interface:** `GET /api/shifts/open-options?fund_id=<int>&business_date=<ISO date>` returns `{business_date,fund_id,point_id,slots:[{code,name,start,end}],can_open,message}`; requires appropriate grant and cashier assignment. Other routes unchanged.

- [x] RED: Test point created today with custom code, tomorrow's renamed or replaced code; assert today/tomorrow are different and invalid code denied on POST today. Test viewer/unassigned clerk, operating days, no side effects.
- [x] GREEN: implement the endpoint using the existing schedule helpers; verify test passes.

### Task 2: Both opening dialogs

**Files:** Modify `static/app.js` and `static/billing.js`; create `tests/browser_s9_shift_open_options_offline.py`.

**Interface:** `setupShiftOpenOptions(form, fixedFundId=null)` attaches handlers and dynamically replaces `form.elements.shift` options; modal already has `setup` hook.

- [x] RED: Browser assert earlier date options differ from later date and fund; billing and central modals; empty/permission-denied disable submit; no horizontal overflow at 375px.
- [x] GREEN: add the shared helper in `static/app.js` and replace stale local choices in both dialogs; verify browser.

### Task 3: Regressions and delivery

**Files:** Update `scripts/ci_smoke.py`, README/current release, project QA and roadmap; produce ZIP, Git bundle, sha256 manifest/release report.

- [x] Run S9 direct + HTTP, browser, S2, S4 in-process/HTTP, CI and broad source suite; record PASS/SKIP/BLOCKED separately.
- [x] Verify extracted archive and clean source lineage; retain NO-GO and blocked V8.0 archive.
