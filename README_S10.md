# Ramses Hospital Accounts S10 — no false incomplete cash day on approved off-days

**TEST ONLY — not deployed or production approved.** Base: S9 `54a3084`; synthetic SQLite data only.

`shift_coverage.report` already distinguishes expected shifts, missing/unclosed shifts, and stations not scheduled to operate on a given weekday (`not_required`). `/api/shifts/day-summary` incorrectly required ALL station daily rows to have `status='complete'`, even if an approved non-operating station had no expected shifts. That created a false provisional cash day despite every *required* shift being closed.

The corrected read-only summary ignores `not_required` entries while aggregating **only when at least one required station is complete**. `not_monitored`, missing, open, grace, submitted, variance and any other unfinished state remain blockers. The `financially_certified` field remains explicitly **false**: completeness of shift coverage is not financial approval. No database migration, ledger, posted amount, roles, grant rules, shift creation or month-close policy changed.

The existing coverage UI now labels `not_required` as an approved no-shifts day. An old offline Chromium fixture was made month-relative instead of hard-coded to October 2026; its 1280px/375px tests also verify the new label. No extra application page.

## Targeted acceptance

```bash
python tests/test_s10_daily_coverage_certificate.py
python tests/test_shift_coverage_v81e_p0.py
python tests/browser_shift_coverage_offline.py
S4_REAL_HTTP=1 python tests/test_s4_integrated_day.py
python scripts/ci_smoke.py
python scripts/qa_g2t_full.py
```

New S10 test first failed (correct RED) with one closed operating point and another `not_required` day. It now checks the correct daily flag, genuine missing windows, no-required and unmonitored-day conservative behavior, owner login, unauthenticated denial and read-only GL/cash/audit invariants. See source-owned test and release QA for fresh run results.

## Not tested by these changes

Physical counting, independently signed daily financial reports, production HTTPS/LAN, hospital printing or real patient funds. Original V8.0 historical migration, physically separate encrypted restore, hospital acceptance, supplier 2200 close policy and independent finance/medical/IT signatures remain blocked. **PRODUCTION NO-GO.**
