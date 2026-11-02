# S7 progress — 2026-11-02

| Priority | Gate | Status / evidence |
| --- | --- | --- |
| P0 | Portable offline recovery drill command | LOCAL TESTED (synthetic) — SHA256 + S6 AES/SQL checks + independent-process ASGI and 401 + fail-closed; `tests/test_s7_recovery_drill.py` |
| P0 | Actual second-computer restore and retained off-site encrypted archive | BLOCKED — requires an approved encrypted backup, independent key control, physical alternate workstation, signed IT/finance/medical UAT |
| P0 | Genuine V8.0 archive migration/reconciliation | BLOCKED — original authenticated archive unavailable; signed opening balance not checked |
| P0 | Hospital browser-to-HTTPS/LAN/receipts/printers and user signoffs | BLOCKED — no authorized staging hospital hardware |
| P1 | Supplier 2200 month-close rule and historic shift-label UI | OPEN — owner/accountant policy and browser evidence required; no silent ledger modifications |

---

# S5 completed locally / next release gates — 2026-11-02

| Priority | Gate | Status | Evidence / next step |
| --- | --- | --- | --- |
| P0 | S4 intermittent HTTP 500 during cashier assignment | **FIXED AND LOCALLY STRESS TESTED** | Cross-thread SQLite `ProgrammingError` and 10s lock timeout both reproduced; synthetic Uvicorn 384/384 at 48 writers, all audits balanced; not hospital load proof |
| P0 | Independent full CI / source-wide regression for S5 | **NOT COMPLETED** | 8 targeted security/finance tests and S4 in-process + HTTP pass; full 66-test run timed out after 5 observed PASS; rerun on dedicated CI worker |
| P0 | Actual V8.0 opening/migration | **BLOCKED** | Verified original source archive and signed opening balance needed |
| P0 | Off-device encrypted recovery and real hospital HTTPS/LAN | **NOT DONE** | Requires separate controlled hardware and authorized UAT |
| P0 | Signed finance/medical/IT operational release | **NOT DONE** | No real patients, funds, supplier settlement or clinical approval used here |
| P1 | Performance and operational concurrency benchmark | **NOT DONE** | Measure realistic shift workload, SLA, sessions, failure retry, checkpoint and burst latency; 48 writers test is synthetic extreme |
| P1 | Accounting policy for supplier 2200 in month-close | **AWAITING ACCOUNTANT APPROVAL** | Define signed exception policy, no silent auto-adjustment |
| P1 | Custom historical shift label | **OPEN** | Reproduce browser display before changing existing records |

---

# Ramses Accounts — stabilization-first delivery roadmap

| Priority | Gate | State | Evidence / pass criterion |
|---|---|---|---|
| P0 | S1 inventory workspaces | verified in synthetic UI | Source baseline S1 tests; no production claim |
| P0 | S2 multi-role financial-day reconciliation | verified in process | `tests/test_s2_cashier_24h_acceptance.py`; 4 closed shifts, 600/50/550 EGP, balanced GL |
| P0 | S2 no duplicate physical deposit | verified in process | `tests/test_s2_treasury_retry.py`; same key replay, different body/person/reference denied, 2-thread race |
| P0 | S2 cash receiver real screen action | verified by browser-to-ASGI bridge | `tests/browser_s2_cashier_treasury_ui.py` at 375/1440 px, not real HTTP |
| P0 | S3 actual local Uvicorn HTTP, sessions, CSRF | verified in synthetic HTTP | Five isolated suites; 4 historical workflows plus login/cookie security; **not browser/TLS** |
| P0 | S3 physical browser HTTPS/LAN/printer | blocked | Chromium sandbox loopback denied; approved staging TLS URL and hospital device required |
| P0 | S4 integrated cashier + patient + bank + procurement + close UAT | verified **synthetically**; hospital UAT blocked | 1 DB, patient and cashier, supplier/bank, prior-paper envelope, 161 HTTP; independent hospital signoffs not done |
| P0 | S5 actual V8.0 migration and independent restore | blocked | Original verified V8.0 archive, balance sheet, recovery hardware and owner sign-off |
| P0 | Source documents/clinical approvals | blocked | Approved signatures, evidence policies and clinical billing rules |
| P1 | Historical shift labels in day-summary UI | source-review finding; not browser-reproduced | `static/app.js` currently resolves labels from latest schedule only and uses `esc(labels[sh.shift])`; confirm past custom code fallback before fixing |
| P1 | Supplier account 2200 reconciliation in month closing | planned | Define exceptions and approved accounting treatment first; never auto-adjust |
| P1 | Central inventory query N+1 and large-ledger pagination | planned | Repeatable 1000/10000-item timing and memory budget; parity invariants |
| P1 | Multi-store stocktake/transfer and documented clinical procedure costs | planned | Start only after integrated release blockers resolved |
| P2 | Physician fees, insurance billing, regulatory e-invoice and formal payroll | not started | Signed business policies / contract models required |

No unverified milestone is a percentage, and passing synthetic scripts is not a production release.

---

## Historical project record — preserved from S1 source

# Ramses V8.1E-G3N — supplier signed statement control / TEST ONLY

- G3M source preserved. Review a *prior completed month-end* supplier statement against the source-attributed GL 2200 balance, including source digest and independent maker-checker. This review does not post opening balance, tax, debit/credit note or bank movement.
- A changed old journal, unmatched AP or discrepancy must remain visible and prevent approval; reject/recreate instead of mutating audit history.
- Local full regression 138 = 132 PASS + 5 SKIP + 1 BLOCKED_NO_V80; zero failures after final source fixes. Independent CI 66/66 PASS; 12/12 browser flows PASS at 320/375/1440; signed release evidence to be attached.
- **Next after G3N:** signed source artifact retention, policy-approved supplier corrections/credit/debit notes and tax accounting, approved independent accounting reconciliation. Production gated on external backup restore, genuine V8.0 and UAT/signoffs.

---

# Ramses Accounts V8.1E-G3I — Gross supplier maturity scheduling / TEST ONLY

- Restored and verified the original G3H source commit `b3cdcd2` and independently developed G3I on `feat/g3i-supplier-maturity` with only synthetic accounts, cases and invoices.
- One to 12 real-calendar installments per approved G3H invoice with exact piaster total, live independent approval, immutable SQL evidence and separate inventory month-close gate. No new payable ledger entries, cash vouchers or payments.
- RTL approval UI requires reviewer-visible amount/date for each installment. Supplier aging is explicitly **GROSS BEFORE PAYMENT**, never actual unpaid balance.
- Frozen authentic G3H schema SQL and independently locally restored encrypted pre-upgrade rollback. See `README_G3I_AR.md`, `RAMSES_V81E_G3I_SUPPLIER_DUE_QA_AR.md` for implementation and current independent QA results.
- **NO-GO:** missing original V8.0 archive, off-device recovery, real supplier/bank docs and approvals, medical/finance/IT UAT and hospital deployment authorization. Next: verified supplier payment allocation and debit/credit adjustment policy; no automated money movement.

---

# G3H — purchasing + three-way document match (1 November 2026) / TEST ONLY

- **Locally implemented:** independent PO approval, linked partial GRNs with exact item/price/quantity caps, independent invoice/GRN/PO match with NO new GL entry (GRN already booked Dr1100/Cr2200); read-only vendor GRN accrual/confirmed/unmatched reports; month-close gates; RTL test UI.
- **Safety:** do NOT auto-post supplier invoice journal or claim AP is settled. Legacy unlinked GRNs are excluded from PO-level match, appear as unmatched GRN accrual; verify actual physical goods and original supplier invoice independent of this reference-only pilot.
- **Next P0:** original V8.0 source/archive, encrypted rollback restore on off-device, real hospital purchase authority/medical/finance/IT signoff, approved procurement budget/custody, clinician verification, quarantine and insurance compliance.
- **Next P1 (G3I):** controlled supplier settlements and debit/credit adjustments with verified bank/cash source, invoice aging/due dates, tax treatment, separate finance approval and prepayment reconciliation (no automatic transfer); later service/vendor pricing, clinicians, insurer claims and patient cost.

---

# حالة أولوية الخصوصية بعد G3E (1 نوفمبر 2026)

- **G3D-08: تم تصحيح مسار الملخص ومراجعة إذن الصرف محليًا في G3E** مع اختبارات كشف المراجع والتفويض المسحوب، وليس قبولًا لإطلاق مستشفى.
- **الخطوة الهندسية التالية P0:** تصميم وإقرار سياسة استقبال المرتجع وحجز الكميات `quarantined` حتى فحص المختص، منع إتاحتها في FIFO ومنع اعتماد صلاحية طبية من موظف مالي، ومراجعة مصير التالف/المرفوض مع قيد محاسبي مستقل غير معدِّل للأصل.
- **الخطوة التشغيلية التالية P0:** أرشيف V8.0 الأصلي، واستعادة مشفرة على جهاز منفصل، واختبارات قبول طبية/مالية/IT وحوكمة الوصول للمعلومات الحقيقية.
- **P1:** أوامر شراء وتوريد جزئي وفواتير موردين ومطابقة ثلاثية ومستحقات، ثم تصحيح كلفة المريض/التأمين والاستثناءات المالية المعتمدة.

---

# G3D next releases — after original-lot case consumables returns (development)

1. **P0 patient/physical safety:** A finance return is *not* clearance for reusing a medical item. Require hospital inventory, infection-control and medical acceptance policy, damaged/quarantine route, and independent clinical reviewer before production.
2. **P0 release gate:** Real V8.0 and G2J/G2K/G2L source archives, independent off-device restore, permissions matrix, separate medical/finance/IT UAT; no production promotion without documented approvals.
3. **P1 traceable corrections:** Reconciliation for case consumables returned to stock versus patient invoices/credits, item scrapping and over/short stock correction without rewriting original GL documents.
4. **P1 privacy:** Fix and test `inventory.overview` issue list case-ID/evidence-ref scoping (G3D-08) for warehouse-only users; use current case-point grants for every result, then rerun negative browser/API tests.
5. **P1 purchase cycle:** Supplier quotation/PO, purchase approval, GRN with partial delivery, tax/vendor invoice 3-way match, AP journal, independent payment request; no bank transfer in software.
6. **P1 doctor and insurers:** Contract effective dates, doctor accrual/split, insurer claims and reconciled settlements; full operation/NICU case cost still unavailable.

G3D original-lot non-drug return flow is implemented locally/test-only, **not** real hospital-ready sterilization clearance.

---

# Ramses Accounts priorities after G3B — 2026-10-31

1. **P0 — Identity & medical governance:** independent clinician registration/licensing verification, authorized medical reviewer, legally valid signature, source-document ownership and retention in HIS/EMR/LIS. SHA-256 proves identical bytes only; G3B medical pilot is not approval.
2. **P0 — Historical resolution:** owner and clinical leader approve a corrective path for old `viewer`/reference-only attestations not yet invoiced; no false witnessing, no silent modification of old invoices.
3. **P0 — Security and readiness:** full endpoint-level clinical/finance RBAC audit, encrypted host temporary uploads, production privacy policy, off-device backup restore, genuine V8.0/G2J/G2K/G2L source tests, monitored hospital UAT and authority signoffs.
4. **P1 — Inventory to patient cost:** G3C read-only approved FIFO consumables cost per case is implemented locally with dual access grants and date-order guards; still needed: clinical issue authorization, batch returns/corrections, opening stock reconciliation, drugs and surgeon/NICU full case cost.
5. **P1 — Accounts payable & professionals:** supplier POs/receipt/vendor invoices/AP, doctor fees, insurer contracts/claims/reconciliation, financial period/year-end with immutable audit trail.
6. **P1 — UX and operational rollout:** bilingual/RTL accessibility, cashier shift print grids, documented training, complete synthetic E2E workflows.

G3B already implemented locally: per-department optional source fingerprint, immutable SHA-256, audited UI/server enrollment and encrypted historic migration. NO-GO production.

## S4 updated gate (2026-11-02)

- **Verified locally:** one SQLite synthetic workday linking patients, 4 physical shifts, historical paper envelope, PO/GRN/invoice, supplier bank voucher, independent bank statement signoff, patient/treasury/2200/GL controls and test-clock month close. Repeatable through TestClient and Uvicorn HTTP (161 HTTP requests); HTTPS browser and actual current-month sealing intentionally remain unverified.
- **Release P0:** original V8.0 archive, off-device encrypted restore and signed hospital finance/medical/IT acceptance are still blocked. Real workstation/browser-to-HTTPS and printer UAT not done.
- **Next P1:** approved 2200 supplier reconciliation policy explicitly integrated into period-close with exception handling and no silent auto-adjustment, and historical custom shift label audit. Hold further UI and business feature expansion until source evidence and cross-role walkthrough are signed.

- **S4 resilience follow-up:** one HTTP 500 arose under concurrent full-suite load while assigning a cashier point. Three independent subsequent network reruns succeeded. Keep investigation open; no root cause or fix claimed. Record server trace under representative load before production.
