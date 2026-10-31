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
