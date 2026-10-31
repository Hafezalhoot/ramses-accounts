# G3C case consumables cost and FIFO chronological integrity (test-only)

## Background
G2T stores immutable, reviewed central non-drug consumable receipts, allocations, GL costs and optional patient-case links. The user has asked to finish patient-level operating/NICU cost accounting, but the existing UI does not show traceable per-case approved FIFO costs. Also, approval of a backdated receipt/issue can retroactively change the implied FIFO ordering after a newer issue has been approved.

## Contract
1. Add a read-only, narrowly authorized `/api/inventory/cases/{case_id}/cost` report. The request must pass BOTH the current warehouse grant and billing-point case scope. It includes only approved FIFO issue allocations for exactly the case, with per-line qty, price from approved lots, item, department, issue id and use date. Include separately a count of pending requests, never add them into approved cost. No patient name, clinical records, doctor fees, profit calculation, extra GL or database writes. Explain totals exclude unlinked issues, drug stock and historical opening balances.
2. Add a small case-cost search/display component to the existing inventory page. Explicit case ID required; show separate totals and source rows on success, and remove older results on forbidden/failed lookup. Use HTML escaping and responsive existing table styles.
3. Preserve existing immutable FIFO valuations by rejecting approval of a new dated receipt or issue for an item if an issue for that item with a strictly later business date was *already approved*. Guard on the API path within the existing `BEGIN IMMEDIATE` transaction and with matching SQLite BEFORE UPDATE triggers. Same-day entries follow approval order because the legacy source has day resolution only. Rejections leave no approved GL, allocations, or phantom stock. No backfill or historical GL revaluation.
4. Upgrade G3B SQLite through existing verified encrypted pre-DDL rollback for the new triggers; existing already-approved data stays untouched. `G3C` is development-only, no production credentials/data or deployment.

## Release checks
- RED -> GREEN real FastAPI synthetic patient case + stock/FIFO lot costs and unauthorized requests.
- RED -> GREEN dated inventory approval chronology and direct SQLite bypass attempts.
- Actual Chromium inventory form on mobile and desktop, no overflow, correct result/error replacement.
- CI smoke + full independent regression; historic V8.0 lack remains blocked, not PASS.
- Source ZIP with SHA-256 per file, isolated extraction tests and Git bundle verification.
