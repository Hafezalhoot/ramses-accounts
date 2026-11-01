# G3I supplier due-term schedules — verified working slice

Source baseline: G3H commit b3cdcd28. Local/test-only; no production data, bank payments, AP postings or tax calculations.

## Invariants
- A validated invoice match from G3H can have one pending/approved due schedule; rejected schedules are historical and permit a corrected replacement.
- Schedule date belongs to the open current period; due dates may be future and must be real ISO calendar dates on/after supplier invoice date. Up to 12 lines, sum in integer piasters must match the approved invoice exactly.
- Scheduling and reviewing are performed by distinct active authorized users; the reviewer must not be the original invoice or GRN preparer, enforced both at API and SQLite trigger boundaries. Pending period closure is blocked.
- Final review documents and their lines are SQL immutable. Idempotent POST uses existing request journal.
- No payment/GL event; outstanding AP cannot be inferred. Aging classifies gross approved supplier invoice schedules and separately reports unscheduled approved invoice total.
- UI shows dated installment details to the independent approver, or hides approval controls when details unavailable.

## TDD implementation
1. Write synthetic API+SQLite regression for end-to-end PO/GRN/invoice+due schedule, approval, revocation, immutability, direct SQL bypass and aging; verify expected RED on missing endpoint.
2. Add tables, integrity triggers and period closure policy to schema.sql and inventory.month_close_inventory_issue.
3. Add minimal FastAPI routes and overview data with existing grants/CSRF, no new external dependencies.
4. Add RTL UI form, review details and gross aging panel; browser-check 320/375/1440.
5. Add frozen G3H schema fixture plus migration/rollback test, CI test registrations and release labels.
6. Run comprehensive QA, browser, archive hash verification and independent extracted ZIP tests; package source Git history and reports. Remain TEST ONLY / NO-GO.
