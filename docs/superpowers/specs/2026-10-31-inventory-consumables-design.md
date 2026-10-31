# G2T: Central Consumables Store (TEST ONLY)

## Intent
Create a minimal, independently-reviewed central consumables procurement and usage subledger, attached to the current general ledger and optional patient case. Preserve existing vouchers, patients, beds and payroll. No cash payments or medical prescriptions.

## Chosen approach
Use existing SQLite transactions, GL journal helper, user roles, CSRF, idempotency infrastructure and app shell. Avoid a separate accounting ledger and new dependencies. For GL `origin`, the existing table CHECK permits manual entries but no new origins; use `origin=manual`, source_id=NULL, and a foreign-key `journal_id` on immutable inventory source documents, thereby allowing `financial_integrity.journal_source` to block manual reversal of source-backed journals. Clearly label these journal entries as system-generated in memo and report. A future schema rebuild can introduce dedicated origins once migration tooling is certified.

## Entity and financial model
- `inventory_vendors`, `inventory_items` (central store, non-drug consumables only), `inventory_access` (explicit owner-issued prepare/approve grants).
- `inventory_receipts` plus immutable `inventory_receipt_lines` (quantity >0 integer units, unit cost integer piasters, one supplier invoice reference per vendor; pending/rejected/approved).
- `inventory_issues` plus immutable request lines, and approved FIFO per-receipt-line allocations.
- Approving receipt requires a second user; in one transaction Dr 1100 inventory Cr 2200 payables. Stock appears only after approval.
- Approving issue requires a second user, verifies stock as-of issue date, consumes FIFO approved lots, Dr 5100 medical supplies expense Cr 1100 inventory, with department cost center and optional open patient case.
- Stock quantity and valuation are derived from immutable approved receipts/issue allocations; no manually writable stock balance.
- Each transaction writes an auditable document and posted, balanced GL source link. Independent reconciliation compares its source rows to linked journal lines.
- No supplier payments, supplier matching to real bank transfers, VAT, returns, expiry-driven drug controls, medical administration or pharmacy dispensing in G2T.

## Constraints and risk controls
- Role owner manages catalog and grants. Clerk with explicit grant prepares; reviewer with explicit grant approves. Owner may perform either with two-person rule.
- No future-dated docs, no mutations in closed accounting periods, no repeated approval, no duplicate invoice reference, no extra quantity from any lot.
- An expired lot cannot be issued. Patient case cost allocation must not expose cases from other cashier points to a clerk.
- Existing generic `inventory_buy` vouchers are historical/unlinked: not counted as new inventory stock. Reconciliation calls out legacy stock and no claim of total inventory certification.
- Dates historical and cash are synthetic only; all real usage is NO-GO pending UAT, source evidence and accountant policy.

## Accepted alternatives
1. Rebuild `gl_journals` CHECK to introduce an `inventory` origin: cleaner classification but destructive migration risk on existing indexed/triggered GL FKs — deferred.
2. Maintain a second stock ledger without GL integration: easier but would present inconsistent cost/asset values — rejected.

## Verification
Real API role/transaction workflow: two receipts, double-submit and duplicate invoice, maker/checker, expense FIFO, insufficient balance, closed case, month lock, immutable source and journal, independent subledger/GL, repeat bootstrap on original G2S frozen schema, existing regressions and browser responsive smoke when possible.
