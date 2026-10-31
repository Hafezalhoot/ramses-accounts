# تسويات بطاقات POS

**وصول المبلغ للبنك يحتاج مطابقة كشف الحساب بشكل مستقل.**

## إيصالات البطاقة المتاحة / سجل التسويات

# Ramses Accounts V8.1E-G2K - POS clearing and acquirer fee settlement

**Date:** 31 October 2026. **Status:** DEVELOPMENT / SYNTHETIC TEST DATA ONLY.
**Base:** Exact G2J project files. **No production deployment or real hospital accounting data.**

## Executive release decision

**NO GO for live hospital finances or patient data.** G2K adds controlled settlement of
patient card receipt parts from a dedicated POS clearing wallet into a target bank
account, net of acquiring fees. A signed bank statement remains mandatory and is
not inferred from a POS settlement. Historic opening balances are unverified.

## Implemented change inventory

1. New `pos_settlements.py`: list unused approved patient card receipt parts;
   submit a batch with acquiring reference and evidence description, immutable
   idempotency key, gross, fee, and bank net; independent decision and audit log.
2. The reviewer must be distinct from the proposer, authorized to approve both
   the POS wallet and destination bank. The proposer must retain authorization
   and an active account. The bank and wallet must be active and distinct.
3. A successful approval commits two linked vouchers in **one SQLite
   transaction**: net POS clearing-wallet-to-bank transfer and acquiring fee
   booked as an expense against GL account `5176`; when fee is zero, only the
   net transfer is created. Original patient receipts and revenue are untouched.
4. New SQLite tables `pos_settlements` and `pos_settlement_parts` include unique
   active payment-part, unique active acquiring reference and DB triggers
   prohibiting updates/deletes to approved settlement evidence. Rejecting a
   pending batch releases parts without posting vouchers.
5. Generic voucher create/approve/reversal paths cannot bypass POS settlement
   to move money from the designated card clearing wallet or reverse individual
   fee/transfer legs after approved settlement.
6. The existing bank sign-off refuses approval while POS batches for that
   bank/period remain pending. The new treasury-to-GL reconciliation checks
   approved POS source receipts and their linked net transfer and fee vouchers.
7. The bank review screen includes an Arabic POS batch panel before the CSV
   bank statement import, with receipt selection, fee/net preview, history,
   independent approve/reject buttons and responsive desktop/mobile layout.
8. `bootstrap.py`, `ledger.py` and the additive schema introduce exactly one
   expense category `pos_processing_fee` and account `5176`. Existing G2I/G2J
   accounts and history were preserved in double-upgrade tests.

## Verified example: money invariants

```
Original synthetic approved patient card receipts       100.00 + 60.00 EGP
Aggregate POS batch GROSS                                   160.00 EGP
Acquirer processing FEE                                       2.00 EGP
NET booked as bank transfer                                 158.00 EGP
Remaining balance in POS clearing wallet                      0.00 EGP
GL acquiring expense 5176                                     2.00 EGP
Duplicate patient revenue/receipt postings                    0
Original patient receipt lines changed                        0
```

Tested replay and duplicate receipt attempts, prohibit self-approval and
unauthorized review, verify two linked approved vouchers, prohibit reversal
of isolated POS legs, and reject direct tampering with approved records.
Bank confirmation was performed separately using an imported, matched,
independently approved synthetic bank statement for 158 EGP. It was not marked
as confirmed by the POS batch alone.

### Negative paths and corner cases

| Scenario | Observed behavior |
| --- | --- |
| POS fee equals the gross | Request rejected |
| Same idempotency key, same request | Original batch returned, no duplicate |
| Same key, changed fee | Request rejected |
| Same card part in another active batch | Request rejected |
| Maker attempts self-approval | Denied |
| Reviewer missing wallet/bank approval grant | Denied |
| Bank statement signoff while POS batch pending | Rejected, even if bank lines match |
| Pending batch rejected by reviewer | Card parts released for a new batch |
| Approved POS transfer/fee reversed alone | Rejected |
| Second bank, batch with zero fee | Posted transfer only, without an expense voucher |
| G2J -> G2K upgrade, repeated twice | Existing users, funds, chart and department retained |

## QA evidence

- **62 successful standalone `tests/test_*.py` scripts out of 63.** The only
  unsuccessful script is `test_billing_upgrade_v81.py`, requiring an exact
  historical V8.0 ZIP not supplied to this project. The missing artifact is
  not evidence that historical migration works.
- `tests/test_v81e_g2k_pos_settlement.py` verifies end-to-end source and
  accounting amounts, rollback/rejection, bank controls and zero-fee branch.
- `tests/test_v81e_g2k_pos_ui.py` renders the actual shipped UI in headless
  Chromium **offline with synthetic API fixtures** at 1440, 375 and 320 px;
  checks checkbox selection, 160 - 2 = 158 live preview, review modal, no
  JS exceptions or horizontal overflow. It is NOT a live HTTP or Mac test.
- `tests/test_v81e_g2k_upgrade.py`: exact G2J -> G2K additive upgrade twice
  using the previous local G2J source tree; no old financial rows deleted.
- `tests/test_v81e_g2j_schema_upgrade.py`: legacy G2I -> G2K additive bootstrap
  updated to require preservation of every preexisting account/category while
  accepting exactly the two legitimate new fee master-data rows.
- `node --check` on old and new JS and `python3 -m py_compile` on backend passed.
- Prior G2J treasury reconciliation, card billing, patient allocations, shift,
  bank, security and other previous tests retained their passing status.

## Scope restrictions / remaining risk register (not implemented)

- Opening bank, cash and clearing-wallet balances **not independently verified**.
  The GL-vs-cashbook match is not evidence of the physical/custodial opening.
- No official acquirer CSV import, cryptographically signed provider statement,
  real provider fee contract validation, or archival attachment proving fees.
- Cross-month bank transfers and late arriving settlements remain an untested
  reconciliation and clearing-account problem requiring an explicit policy.
- Chargebacks, reversed card charges, partial refunds, multiple POS terminals,
  separate acquirers, terminal-level batches and dispute reserves are not
  implemented in this milestone.
- Booking the net into the bank ledger occurs upon independent POS settlement
  approval, before actual independent bank-statement signoff. Final production
  policy may require an in-transit account until the bank actually credits it.
- No assurance of tax/legal correctness of merchant fees; obtain accountant's
  determination for VAT, commissions and fiscal evidence.
- Hospital clinical invoices, inpatient admissions, intensive care/neonatal
  beds, surgical bills, stock depletion, vendor accruals and doctor settlement
  workflows still require major further work.
- Data residency, patient data privacy controls, encrypted off-device restore,
  network multi-user deployment and live device/shift acceptance are still
  unverified. Do not process real patient information or money.

## Next recommended G2L priority

1. Design an independent sign-off of **opening balances per fund**, backed by
   statement/physical count/provenance, with dated ledger initialization and
   strict maker-checker controls. Preserve original balances and prohibit
   arbitrary later edits.
2. Define POS-in-transit and cross-month settlement policies with the finance
   lead, then extend reconciliation to acquirer CSV imports and chargebacks.
3. Continue actual inpatient / OR / nursery costing, patient discharge, stock,
   vendor and physician payment workflows; build a release acceptance pack
   for 3 external and 1 central cashier shift.

## Trial usage on Mac

Unzip to a writable folder, open `ramses_accounts`, then
`START_Ramses_Mac.command` and select the **Local DEMO** option. Use synthetic
patients and balances. Do not replace an existing working data directory.
Mac Finder Gatekeeper, live HTTP, live payment-provider, real bank, real payroll,
production backup and recovery were not verified.
