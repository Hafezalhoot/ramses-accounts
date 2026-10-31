# Ramses Accounts — project roadmap after G2U

| Slice | Objective | Gate | State |
|---|---|---|---|
| G2V | Encrypted verified pre-upgrade rollback, legacy restore and fail-closed key | Synthetic migration+restore tests + CI/full QA | locally tested; offsite/UAT pending |
| RBAC next | Endpoint matrix for read/export/attachment/printing/reporting of financial and personnel data | Role x object x action negative tests, financial owner policy | not started |
| Clinical next | Clinician-signed service-fulfillment event separate from financial billing | Real attestable actor, immutable evidence, revocation, audit and reconciliation | not started |
| Suppliers next | Purchase orders/receipts/invoices/credits/settlement matched to inventory/AP/GL | Matching reconciliations and independent approval | not started |
| Operations / physician / insurance | Medical resource cost, doctor accruals, insurer cycles | End-to-end subledger -> GL -> close | not started |
| Release | Offsite encrypted restore, actual hospital UAT, trial parallel operations | Signed approvals finance+clinical+IT+management | blocked |
