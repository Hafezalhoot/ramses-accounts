# Ramses Accounts — Project Autopilot status

Last audited: 2026-10-31. **Current source: V8.1E-G2S** (based on G2R, backed by Git history). **Status: tested locally on synthetic data; NO-GO for production.** Nothing was deployed to a hospital system. There is no verified remote CI or offsite restore.

## Implemented in this increment

- Owner-only, idempotent and atomic bed transfer with independent immutable evidence; no GL entry or clinical discharge.
- Month-close gate independently checks dated bed nights from all earlier patient admissions, reconciles ordered nights with issued and posted GL journals for the appropriate month, and refuses unresolved periods.
- Database triggers prevent retroactive changes to closed periods, stale date-effective tariffs, unauthorized mutation of transfer records, and cross-case misassignment.
- Historical private June preview workbook is omitted from exported ZIP. Missing fixture gives an explicit archive error and test SKIP, not invented hospital financial data.
- G2R original schema fixture upgrades twice to G2S without losing synthetic patient, stay, tariff, night or audit records.

## Test status

Full test inventory executed individually: **91 scripts: PASS 85, SKIP 5, BLOCKED/FAIL 1**. One blocked historic `test_billing_upgrade_v81.py` requires original V8.0 ZIP. Two skipped historical June workbook previews; three skipped historical upgrade fixtures. See `QA_G2S_TEST_RESULTS.tsv` and `RAMSES_V81E_G2S_TRANSFERS_QA.md`.

CI smoke script is a local test gate only, not a deployment or proof of a remote GitHub run. G2S source ZIP contains no live DB or uploaded patient data, private workbook, or credentials.

## Current business rules are NOT approved

- Midnight-calendar-night billing is a **proposed** trial policy, not hospital-authorized charging. Intraday proration, payer contracts, transfers, refunds and medical sign-off are unresolved.
- Operational transfer belongs to owner in this prototype; clinical admission/ward/nursing custody roles are not implemented.
- Long-stay accrual and automatic monthly postings have not been implemented. Existing G2R >366-day limit needs a monthly cursor and pagination.
- Cashier, banks, accounting and patient clearance have passed scoped tests but are not independently accepted for real funds or sensitive patient information.

## Next three highest-value actions (pending authorization and accounting policy)

1. M4c: hospital-approved room/ICU tariff-day cutoffs, in-period accrual vs invoice, long-stay monthly invoice cursor; test multi-month balances and correction paths.
2. M6: purchase orders, vendor AP, goods receipts, lot/expiry, stock valuation and per-case consumable allocation with no negative stock or duplicate expense.
3. M5/M7: surgical and neonatal consumables/costing plus physician accrual/settlement, cross-ledger reconcile; then independent staff/finance acceptance.

**Release gate: NO-GO** until clinical/finance acceptance, full RBAC, historical migration, real device rehearsal, and verified encrypted off-device backup restore. No production bank, patient or money actions without a separate approved migration/rollback plan.
