# G3F — Medical quarantine for returned non-drug consumables (TEST ONLY)

## Intent
Prevent any financial approval of a case consumable return from making its returned lot available for another patient's issue before independent, department-authorized clinical inspection. Keep source FIFO allocations, case costing and GL journals immutable.

## Approaches considered
1. Delay the financial return until clinical inspection: rejected, because it conceals physically returned hospital-owned inventory and distorts the original case correction.
2. **Chosen:** retain the existing accounting return (Dr stock/Cr consumables) and mark approved returned units quarantined by default. Add an immutable per-return-line clinical disposition; only a positive dated release increases FIFO availability.
3. Create a full regulated sterile-processing/UDI/stock-location subsystem: deferred until the hospital approves a validated clinical policy, warehouse segregation and financial disposal process.

## Contracts
- A positive `inventory_return_inspections` record is required for each returned allocation before its quantity can be reused; absence of a record (including all G3D historical returns) means quarantine. Negative disposition remains quarantined; disposal/write-off is not silently performed.
- Inspector must be an active, owner-reviewed clinician with a current department grant; financial owner, clerk and reviewer cannot clinically approve. The clinical queue is department-scoped and never exposes patient, billing, accounting or supplier prices.
- An inspection is indivisible per returned source lot/quantity; partial release requires separate physical return-line documents. A safety attestation of unused, intact and infection-control clearance plus a reference and note is required for release. A release date may not predate the physical return, be in the future or fall in a financially sealed month. An expired lot cannot be released. Inspections are append-only and immutable. No changes to historical GL or pricing.
- FIFO application **and SQLite direct write guard** use only independently released returns available by issue date; tests cover role revocation, bypass attempts, identity, immutability, repeated approvals, partial returns, ledger reconciliation and legacy upgrade. Existing G3D tests that reuse returned lots must include an independent G3F inspection first.
- Stock report separates on-hand ownership, conservative quarantined quantity and usable quantity. Expiration and other clinical restrictions still apply at actual issue approval; this is not a guarantee of clinical fitness.
- Older G3E return units that were historically reissued without a medical inspection must not be silently certified; any legacy overdraw risk remains documented for manual reconciliation. No production migration, medical release or payment authorized.

## Non-goals
Clinical license verification, actual infection-control policy certification, medical reprocessing, disposal accounting, drug/pharmacy tracking, multiple physical bins, deployment, real patient data.

## Gate
Local and encrypted migration verification only; production NO-GO pending clinical/financial/IT signoff and independent restore drill.
