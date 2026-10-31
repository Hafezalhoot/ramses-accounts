# Ramses Accounts — project roadmap after G2U

| Slice | Objective | Gate | State |
|---|---|---|---|
| G2V | Encrypted verified pre-upgrade rollback, legacy restore and fail-closed key | Synthetic migration+restore tests + CI/full QA | locally tested; offsite/UAT pending |
| G2W | Deny unscoped viewers from global GL journal/trial balance exports | Local API regression | locally tested; no global reviewer policy |
| G2X | Restrict sensitive cashier shift listing, details, evidence and decisions per fund grant | TDD HTTP negative/positive, revocation, 104-script full gate | locally tested; finance RBAC policy not signed |
| Reporting next | Approve global chief-accountant scopes, reviewer GL, viewer monthly financial and patient reconciliation | Business policy + per-object negative HTTP tests | pending policy |
| RBAC next | Endpoint matrix for read/export/attachment/printing/reporting of financial and personnel data | Role x object x action negative tests, financial owner policy | not started |
| Clinical next | Clinician-signed service-fulfillment event separate from financial billing | Real attestable actor, immutable evidence, revocation, audit and reconciliation | not started |
| Suppliers next | Purchase orders/receipts/invoices/credits/settlement matched to inventory/AP/GL | Matching reconciliations and independent approval | not started |
| Operations / physician / insurance | Medical resource cost, doctor accruals, insurer cycles | End-to-end subledger -> GL -> close | not started |
| Release | Offsite encrypted restore, actual hospital UAT, trial parallel operations | Signed approvals finance+clinical+IT+management | blocked |
