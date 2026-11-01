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
