# S4 - single-database hospital financial-day acceptance

Baseline S3 commit: 4e425e4. Synthetic test-only SQLite, no production config/data.

Goal: prove cashier custody, real patient invoice/collection, cash expenses, supplier PO-GRN-invoice-payment, bank matching and GL/subledger reports can coexist in one database without duplicates or unexplained deltas.

Acceptance slices:
1. One Cairo business date: 3 sequential external cashier shifts and 1 internal shift, independent handover, receipt and approval. First shift must collect a genuinely issued 100 EGP patient invoice, not just a generic receipt. Other shifts add 200 and 300 EGP receipts. Central treasury receives exactly 600, spends 50, ends with 550.
2. Independently approved supplier PO/receipt/invoice creates 100 EGP AP; 60 EGP bank payment requires different reviewers. Source-attributed GL 2200 ends at 40, and bank statement is reconciled and approved.
3. A historical mixed-paper envelope can be reconstructed in the same database without changing the original sealed period or collecting already held patient cash twice.
4. Read-only patient and treasury reconciliation, supplier 2200 report and journal totals match. Negative guards for duplicate deposits, unauthorized cash custody, unapproved supplier payment, missing bank signoff, and premature period close.
5. Actual calendar clock must NOT be bypassed in production. For an optional fully completed month-close gate, a test fixture may simulate past-month time only inside an in-process sandbox; clearly label the simulated clock and synthetic schedule configuration.
6. Test-first if a concrete defect requires production changes. No new business modules, regulatory claims, bank movement outside disposable DB, or live deployment.

Known limitations: the hospital's original V8.0 archive, real bank invoices, physical source signatures, browser-to-HTTP under TLS, and off-device restore remain release blockers.
