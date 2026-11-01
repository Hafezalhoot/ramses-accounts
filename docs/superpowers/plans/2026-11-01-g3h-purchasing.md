# G3H — controlled non-drug consumable purchasing / TEST ONLY

## Context and selected design
G3G's already-approved receipt debits 1100 stock and credits 2200 suppliers. Creating a second invoice journal would duplicate AP. Preserve legacy receipts and original journals. Use additive purchase-order, purchase-order-line, receipt-to-PO link and supplier-invoice-match tables; the legacy receipt with no PO link remains grandfathered/explicitly unmatched. Do not mutate G3G receipt table or source history.

## Core workflow
1. Inventory preparer creates an immutable PO for one active vendor with one or more distinct active non-drug items, quantities and fixed positive unit prices, order date and external document reference. Request key is idempotent. Independent inventory approver approves/rejects, no posting.
2. Inventory preparer creates an existing GRN with optional `purchase_order_id` to link it. Under BEGIN IMMEDIATE link validates PO approved, same vendor, receipt date >= order date, exact original unit cost, registered SKU, quantities bounded by total approved/pending linked deliveries. GRN approval rechecks same conditions; rejects release reserved quantity. Old GRNs stay unchanged and unlinked.
3. For approved PO-linked receipt, preparer records matching supplier invoice evidence/date/declared exact amount; reviewer independently accepts/rejects. The matching itself never creates a new journal: 2200 AP was posted by GRN. A mismatch is rejected, never silently adjusted, no tolerance, no VAT/FX inference. Match is immutable when final; rejected proposal can be resubmitted with a different request key; receipt can have only one active match.
4. Read-only supplier accrual summary highlights per-vendor GRN-backed 2200 and confirmed/unmatched portion, *not* a bank AP settlement or full enterprise liability.
5. Current-month pending matches and PO-linked approved but unmatched GRNs block pilot month close; old/legacy GRNs don't retroactively block. No payments, pharmacy, patient treatment, taxes, multi-currency or live deployment.

## Non-negotiables
API and SQLite source guards; active grant recheck under write lock; independent reviewer; original document integrity, no overbooking, idempotency and fail-closed; no automatic external bank action. DDL only on isolated local branch, frozen G3G fixture, encrypted pre-upgrade rollback and independent restore.

## TDD/tasks
1. Build synthetic real FastAPI+SQLite test for create/review PO, partial receipts, wrong vendor/price/overbook/PO status, duplicate request, dynamic grant, invoice mismatch and independent approved matching, unchanged 1100/2200 GL and AP report. Run RED.
2. Add additive DDL with trigger guards; implement PO + invoice API and receipt links. GREEN.
3. Add minimal RTL PO/GRN/invoice matching forms and AP summary; test Chromium mobile/desktop.
4. Add frozen authentic G3G schema migration/rollback test, close-month guard and CI registration; run RED/GREEN.
5. Full regression, isolated CI, browser, ZIP manifest/SHA/git bundle, extracted verification; NO-GO pending production approvals.
