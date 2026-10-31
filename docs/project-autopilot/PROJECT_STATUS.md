# Ramses Accounts — Project Autopilot status (G2T)

**Observed source:** V8.1E-G2T developed from the exact G2S ZIP; operating only in synthetic local tests, not deployed. **Production: NO-GO.** Existing Git history G2P→G2S retained, G2T commit added locally.

## New implemented/tested source

- Central **non-drug** consumables stock, vendor/item catalog, receipts and issues with owner-issued prep/reviewer authorization, FIFO allocation by approved receipt lots.
- Review-approved receipts: Dr GL 1100 / Cr 2200; review-approved issues Dr 5100 / Cr 1100. No supplier cash payment, VAT treatment or patient invoice posted automatically.
- New source-linked inventory journal reconciliation in period close; not a certification of previously untracked historical inventory in GL 1100.
- Approved document immutability, closed-period guards, one approval under concurrency, no negative stock, double-check reviewer grants inside write transaction.
- Frontend RTL tested offline 1440/375/320; server app status and launcher release labels aligned to G2T.
- Original G2S SQL schema upgrade twice into G2T; patient/GL/shift tests retained.

## Evidence

- 97 Python tests: 93 PASS (combined split-suite runs plus targeted post-fix reruns), 3 SKIP (missing old schema source archives), 1 BLOCKED (missing original V8.0 archive). No general-purpose 97-test one-process run claimed.
- 25/25 local CI smoke tests passed in an independent parallel test run after feature and authorization fixes.
- Files: `RAMSES_V81E_G2T_INVENTORY_QA_AR.md`, `QA_G2T_TEST_RESULTS.tsv`, `QA_G2T_CI_25_TEST_RESULTS.tsv`.

## Outstanding safety and product issues

- Unapproved hospital procurement/tax and drug policies, supplier payments/refunds, purchase orders, multi-store stock count and pharmacist controls.
- Existing GL `inventory_buy` vouchers bypass the G2T **physical** quantity subledger; source-only reconciler does not certify the entire historical 1100 asset balance.
- No complete doctor costs, surgery/neonatal costing, real hospital RBAC/restore/production UAT; no real network or bank acceptance.

## Next three executable slices

1. Purchase orders, vendor reconciliation and proof-backed payments/refunds—test supplier balance and bank match.
2. Approved multiple warehouses, transfers, stock count/variance, case-level cost allocation—negative quantity and closed month concurrency tests.
3. End-to-end finance/security UAT, off-site encrypted restore and evidence sign-off before **any** real deployment.
