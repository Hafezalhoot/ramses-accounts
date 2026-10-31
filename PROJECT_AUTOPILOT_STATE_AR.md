# Ramses Project Autopilot — state after G2R

- Base: G2Q frozen source ZIP. G2R extends `schema.sql` additively, `bed_stays.py`, `case_settlement.py`, `bootstrap.py`, `app.py`, `static/billing.js`, tests and trial labels.
- M0/M1/M2: partial; repository/CI not deployed, comprehensive privileges and audit external anchoring remain open.
- M4: **in progress**. Bed master, administrative occupancy intervals, date-effective quote, explicit ordered nights, SQL collision/immutability and patient case clearance gates **tested locally**. No approved bed tariff policy, medical discharge module or actual operating day-based invoice accrual.
- M3: cashier/GL/POS still trial; M5-M8: inventory/suppliers, OR/NICU consumables and doctor fees remain unimplemented.
- Test detail: `QA_G2R_TEST_RESULTS.tsv` and `RAMSES_V81E_G2R_BEDS_QA_AR.md`.
- Genuine old V8.0 ZIP missing: historical upgrade test cannot pass; do not fabricate an archive.
- NO GO for production. No deployment, no live bank connections, no hospital data. Safe next 3 slices: (1) clinical service verification and sign-off for tariffs; (2) bed transfer/long admission accrual across month close; (3) inventory receipts/issues and patient costing with subledger.
