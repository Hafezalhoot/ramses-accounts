# S13 — External cashier and printable documents

User request: continue actual development, provide an external cashier preview account, demonstrate patient invoices, receipts and shift close, and make alternating Chat/Work recoverable.

Design choice: retain existing billing, cash/GL and independent handover rules. Add authenticated, read-only Arabic print views of issued invoices, collection receipts and shift daily reports. Reuse existing object authorization and blind-count redaction; do not print the entire application or invent payment/clinical approvals. Escape all database text. Use local Cairo assets and an external script compatible with the existing CSP. Support A4 and narrow receipt layouts through the browser printer settings. Printed documents retain the TEST ONLY notice.

## Implementation plan

- [x] Regression first: isolated real API scenario creating a cashier, patient, priced service, fulfilled line, issued invoice, payment and independently closed shift. Check anonymous/foreign/revoked access, escaped text, print totals, open-shift blind counts and read-only behavior. Observe missing print endpoint failure.
- [x] Implement `print_documents.py`, local print CSS/JS, links from invoice/receipt/shift screens, and router registration. Verify the regression turns green.
- [x] Exercise the actual cashier browser journey at mobile/desktop widths, print-to-PDF and independent treasury/reviewer handover. Inspect rendered output.
- [x] Create explicit synthetic preview identities and isolated cash funds using authorized APIs. Provide private access instructions and a cashier walkthrough. Keep secrets and databases outside source archives.
- [x] Independent code review; full regression including original V8.0 archive; record PASS separately from unavailable-fixture SKIP. Update state, commit source, bundle history and delivery hashes.

Review focus: object-level access after grant revocation; original receipt after allocation correction; cards versus physical cash; submitted versus finally approved close; print escaping and browser CSP; no account/ledger mutations on print GET.

Scope: S13 completes this cashier demonstration slice. FIN-01 month-end policy, procurement/supplier/doctor/insurance lifecycle, off-device recovery and hospital UAT/signatures remain separate operational gates.
