# Project Autopilot — Ramses Accounts V8.1E-G2S QA and release notes

**Status: DEVELOPMENT / SYNTHETIC TEST ONLY — NO-GO FOR PRODUCTION.**
**Date:** 2026-10-31. **Source:** archived original G2R ZIP; all modifications are additive, never a live DB migration.

## Implemented and independently exercised

| Finding | Change | Verification |
|---|---|---|
| M4-B01: missing bed-transfer handoff | Owner-only POST `/api/beds/stays/{stay_id}/transfer` atomically records old release, new admission, immutable `bed_transfers` evidence and append-only audit; idempotent retry | `test_v82_g2s_bed_transfers.py` |
| M4-B02: incorrectly scoped month close | `month_close_bed_issue` checks expected nights and invoicing for each service month, not only case admission month; shared `check_period_close_ready` blocks unresolved periods | `test_v82_g2s_month_end.py` |
| M4-B02b: wrong-month GL post | A period-scoped bed invoice is accepted only if its GL journal is actually posted within that same month; an earlier document date alone cannot certify revenue. | `test_v82_g2s_month_end_ledger_date.py` |
| M4-B03: closed-month physical backdating | API and SQLite triggers prohibit admission, release and night charges dated in a sealed month; release date cannot precede booked night | `test_v82_g2s_closed_bed_period.py` |
| M4-B04: stale tariff data integrity | New SQL trigger ensures `bed_night_charges.price_version_id` is the latest version effective on night date; legacy positive rate is no longer sufficient | `test_v82_g2s_tariff_integrity.py` |
| M4-B05: bed transfer UX | Arabic RTL owner-only transfer action, available compatible target beds, immutable transfer history; existing service invoices preserved | `test_v82_g2s_bed_transfers_ui.py`: isolated Chromium 1440/375/320 |
| M0-ARCHIVE: G2R update safety | Frozen original G2R `schema.sql` persisted as fixture; additive G2S migration tested twice preserving historical patient, bed, night charge and audit rows | `test_v82_g2s_upgrade.py` |
| M0-PREVIEW: missing private workbook | `--archive` now errors before creating an empty preview. Workbook-dependent tests explicitly SKIP if the deliberately withheld original June XLSX is absent | `test_v82_g2s_preview_archive_guard.py`; two explicit skips |

## Known constraints / not implemented

1. **No hospital-approved tariff or night policy**: calendar midnight transfer, no intraday proration, insurance tariff, medical discharge signature, or policy for changing beds on the same date.
2. **No full long-stay revenue accrual**: the month-close rule currently requires a posted invoice by period end. It does not post automatic GL accruals. The exact legal/accounting treatment of open inpatient stays must be approved.
3. **Current G2R preview query can reject a single stay longer than 366 calendar days**; rolling multi-year stays and periodic cost settlement need a bounded monthly cursor.
4. **Clinical custody RBAC**: physical admissions/releases/transfers remain owner-only, temporarily. Proper admission/nursing/ward workflows, authorization and accountability are not implemented.
5. **Inventory, purchases, suppliers, operating-room/NICU consumables, physician entitlements, historical V8.0 migration and real device tests remain open.**
6. SQLite immutability is not tamper-proof against an OS/database owner; encrypted offsite backups and independent append-only audit system are not verified in real operations.
7. The **historical 618-row preview workbook is deliberately excluded from this ZIP**, so the two fixture-dependent tests skip rather than silently inventing real monetary data. Use LOCAL DEMO for generated synthetic transactions.

## Verification register

See `QA_G2S_TEST_RESULTS.tsv` for per-test outcomes (including skips and blocked historical upgrade) and `BUILD_MANIFEST_V81E_G2S.json` for per-file hashes. Smoke/ZIP verification is recorded separately in delivery notes. No production deployment or live patient/financial data.

## Next prioritized slices

1. M4c: policy-approved charge windows and month-by-month long stay billing/accrual with a controlled ledger, multi-year read pagination and reviewed corrections.
2. M6: vendor purchasing, inventory receipts/issues, lot/expiry, stock valuation and patient-case cost ledger with independent review.
3. M5/M7: OR/NICU costing and physician remuneration integrated to patient cases and ledger; complete least-privilege RBAC.

## Final fresh source-suite results (2026-10-31)

The 91 source `tests/test_*.py` entrypoint scripts were executed individually in isolated scratch directories; see `QA_G2S_TEST_RESULTS.tsv`:

- **PASS 85** (including G2S transfer, month-close journal date, tariff, closed-period, web UI and frozen G2R schema upgrade tests).
- **SKIP 5**: two private June 2026 preview-workbook checks deliberately omitted from distributable ZIP, plus three historical upgrade fixture checks for absent source archives.
- **FAIL / HISTORICALLY BLOCKED 1**: `test_billing_upgrade_v81.py` requires original V8.0 source archive not available in the build environment. This is not counted as success.
- No other failed source tests observed in this run. Production acceptance remains **NO-GO**.

## Release-oriented local CI gate

Ran `python scripts/ci_smoke.py` on the frozen G2S source: **20/20 passed, process exit code 0**. This is a local source check only; no remote CI, hospital deployment or physical terminal test is claimed.
