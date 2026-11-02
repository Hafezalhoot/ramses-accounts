# Ramses Hospital Accounts — S9: effective-dated cashier shift opening

**TEST ONLY — PRODUCTION NO-GO.** This version is a local synthetic-source build. No genuine hospital users, patients, ledgers, funds, database or deployment were changed.

## Problem and correction

Cashier shift-opening dialogs in the general cashier day and patient-billing areas formerly populated choices from the *latest saved* collection-point shift plan, even if that plan only starts tomorrow. The server's POST correctly rejects codes invalid on the selected day, but the on-screen choices confused cashiers and could waste time during physical handover.

Both dialogs now query the same read-only authenticated endpoint:

```
GET /api/shifts/open-options?fund_id=<int>&business_date=YYYY-MM-DD
```

The response contains `business_date`, `fund_id`, `point_id`, `slots`, `can_open` and `message`. Effective-dated slot labels, clocks, allowed weekdays, point lifecycle, assigned cashier, per-clerk allowed shift codes and protected-fund permissions are checked on the server. Legacy funds not mapped to a cashier point retain the original shift templates. Future plans can be previewed, but their shifts cannot be opened early.

The browser re-requests choices on fund/date changes; stale responses cannot overwrite newer ones. The confirm button is disabled during loading, on errors and when no valid shift is available. The unchanged `/api/shifts/open` POST remains the sole authority and rechecks access, chronological custody, closed accounting periods and opening restrictions inside its transaction.

No GL rules, table schema, posted amounts, grant allocations, audit trail, historical shifts or old financial reports were modified. Existing S8 historical shift labels remain date-correct. This release did not add a new screen.

## Verification performed on the S9 source

- API regression `python tests/test_s9_shift_open_options.py` PASS; its test first failed when this endpoint was absent.
- Genuine local TCP Uvicorn HTTP `python scripts/qa_s9_http.py` PASS with **33 requests**, distinct authenticated sessions and negative role checks.
- Offline Chromium JavaScript fixture `python tests/browser_s9_shift_open_options_offline.py` PASS at 1280px desktop and 375px mobile, including rapid stale requests and both opening dialogs. This is not browser-to-hospital-HTTPS proof.
- Independent CI `python scripts/ci_smoke.py` **70/70 PASS, exit 0**.
- Full source regression `python scripts/qa_g2t_full.py` **146 scripts: 140 PASS, 5 SKIP, 1 BLOCKED_NO_V80, zero FAIL/TIMEOUT, exit 0**. The unavailable original V8.0 migration is not a PASS.
- Integrated S4 synthetic financial day with a separate Uvicorn HTTP server **161 requests PASS**; central treasury EGP 1,850, supplier payable EGP 40 and bank EGP 140, all GL debits equal credits. No real cash processed.

Detailed evidence: `QA_S9_*` artifacts, `docs/project-autopilot/TEST_REPORT.md`, `docs/project-autopilot/S9_EFFECTIVE_SHIFT_OPEN_SPEC.md`. Arabic operating summary: `README_S9_AR.md`.

## Remaining blockers — hospital PRODUCTION NO-GO

Authentic V8.0 archive with reconciled opening balances; witnessed encrypted recovery on another physical computer; actual cashiers' workstations over HTTPS/LAN, printed receipts and attached evidence; independent finance, medical and IT sign-offs; accountant-approved supplier control account 2200 month-close exceptions. No deployment or production migration was performed.
