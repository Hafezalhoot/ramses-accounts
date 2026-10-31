# Ramses Accounts V8.1C - verified milestone

## Delivered and checked
- Configurable Cairo cashier shift templates. Default starts: night 00:00, morning 08:00, evening 16:00; next start is previous end. Times may change.
- Business date = local start date. Midnight-start night is attributed to the new date.
- Second-person cash handover and separate independent accountant signoff; resubmit on recount.
- Station-level shift daily cash report and owner/reviewer consolidated daily receipts.
- Issued invoice credit requests and independently approved credit journals (contra-revenue 4195, AR 1200, patient-refundable liability 2310).
- Cash or matched-method electronic patient refunds require separately approved request and actual till payment; prepayment refunds debit advances liability 2300.
- Protected cashbook generic voucher reversal and manual credit journal reversal.
- Browser: billing and shifts responsive at 1440px and 375px; all six isolated Chromium scripts passed.
- Tests: 29 Python test_*.py files passed independently, including new credit/refund/shift and historical migration tests. No real credentials or patient records used.

## Still blocked before real financial operation
- Strict actual-shift clock check defaults OFF in demo; must define and enable on hospital system.
- No full NICU/inpatient complex billing or POS-to-bank settlement reconciliation automation.
- No complete insurance/contractual fee or patient discount policies, legal Egyptian tax invoice compliance.
- No inventory consumption, supplier AP and doctors' fee payables integrated into clinical case cost/real departmental profitability.
- No independently verified off-device encrypted restore or tested real Google Sheets service-account sync.
- Real multi-cashier concurrency tests, penetration testing, operations signoff and policies still required.

## Launch
Extract ZIP into a *new* directory on your Mac, retain the old V8.1B directory, run START_Ramses_Mac.command. Demo records are separate from production data; never overwrite a database on a Mac without verifying backup/restore. The new functions are development-only.
