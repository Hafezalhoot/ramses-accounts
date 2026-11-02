# S9 - Effective-dated options when opening a cashier shift (TEST ONLY)

Problem: Both cashier opening dialogs use the most recently saved station schedule or global three-shift template, even when a newer version starts tomorrow. The write API already enforces `cashier_ops.slots_for(point, business_date)`, so the UI can offer a choice that the server will reject. Different tills may also have entirely different shift codes.

Approved approach: one read-only route `GET /api/shifts/open-options?fund_id=...&business_date=YYYY-MM-DD` returning the same effective-dated station slots that the actual write route verifies, and a shared browser picker bound to fund and business-date changes. Reuse the existing station schedule and authorization checks, not a second scheduling model.

Acceptance:
- Current date must yield the current version even with a future version stored; a future preview must reflect its future version but may NOT be submitted to the opening route.
- No shifts on non-operating days, inactive stations, or unassigned shift codes for a clerk. Deny viewers, unassigned clerks, and users lacking protected-fund grants. Unmapped legacy cash/wallet retains the global templates.
- Both the central shift screen and the billing-specific shift modal requery when the business date changes; the central screen also requeries on fund change. Labels and times must come from the returned slot, not names hardcoded by code.
- Loading/empty/errors disable confirmation; late responses cannot replace newer selections; user-visible accessible status text; actual POST remains the final authority. No new financial posting, migrations, roles or edits to previous shifts.
- API read produces no GL, fund movement, audit or shift session writes; tests include real FastAPI sessions, negative role/branch, and Chromium desktop/mobile. Existing S2/S4 financial acceptance remains green.

Not approved: changing month-close rules, supplier 2200 accounting policy, production migrations or hospital deployment.
