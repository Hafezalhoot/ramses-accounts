# Current: Ramses Accounts G3N-S9 - effective-dated shift opening / TEST ONLY / NO-GO

From S8 `ac090681`, both cashier and patient-billing opening dialogs use the same read-only, access-scoped `/api/shifts/open-options` source that resolves a point's schedule by selected Cairo business date. Future schedules are preview-only; closed weekdays and ungranted shift codes cannot be selected; pending requests do not overwrite newer choices. The actual `/api/shifts/open` transaction remains unchanged and authoritative. No schema, ledger, grants, money, historic records or production data changed. See `README_S9_AR.md`, `README_S9.md`, source-owned HTTP/browser tests and release evidence. Physical V8.0/HTTPS/off-device/finance approvals remain NO-GO.

---

# Current: Ramses Accounts G3N-S8 — historical cashier identity / TEST ONLY / NO-GO

From S7 `67cbdf8`, recover original names of recorded cashier shifts from the point's **effective-dated schedule for the recorded business_date**. The shifts list, hospital cash-day summary and per-shift daily report now include `shift_name`; desktop/mobile/report UI displays it rather than the latest schedule's label. A frozen-date browser fixture was repaired. Tests: source-owned S8 API, offline Chromium, genuine loopback HTTP, S2/S4 accountant workflows and controlled regression. **No schema, ledger, role, price, monetary movement or production data changed.** Hardware/TLS/V8.0 and hospital approvals remain blocked. See `README_S8_AR.md`; release-gate results in `docs/project-autopilot/TEST_REPORT.md`.

---

# Current: Ramses Accounts G3N-S7 — portable offline recovery drill / TEST ONLY / NO-GO

**Verified source S7 gates:** CI 68/68 PASS; source suite 144 = 138 PASS, 5 SKIP, 1 BLOCKED_NO_V80; independent S4 Uvicorn HTTP 161 PASS. These are synthetic local gates only, not the hospital release gate.

From S6 `8feca982`, added source-owned `scripts/recovery_drill.py` for hospital IT to run **manually** on a separate encrypted workstation, with independent source-file SHA256, safe no-clobber restore, a disposable copy for a separate-process FastAPI health/deny smoke, and a PII-free JSON report. New regression includes wrong hash, wrong key, tampered AES, existing/symlink destination, no overwrite; no hospital data, schema/GL/UI changes, remote copy, auto cutover or signed off-device verification. See `README_S7_AR.md`. Full CI and release evidence recorded separately. Production NO-GO until physical external recovery, V8.0 migration, real HTTPS/LAN and authorized finance/medical/IT acceptance.

---

# Ramses Accounts G3N-S6 — encrypted backup business-integrity gates / TEST ONLY / NO-GO

Starting from S5 `38b2720`, S6 hardens `scripts/secure_backup.py` and its test suite: reject posted GL imbalance, stored voucher/shift/bank source checksum mismatches and missing principal financial immutability triggers even when SQLite structure/FK checks pass. A new synthetic recovery drill copies encrypted `.rbe` evidence to a separate directory, restores through a new Python process, compares full content fingerprints of critical tables and authenticates the restored app. This is **NOT an off-device drill** and cannot substitute for V8.0 authentic migrations or hospital UAT. The CI smoke list now includes the new S6 regression (**67/67 PASS**, fresh local run), and S4 integrated HTTP acceptance was retested (**161 requests PASS**). See `README_S6_AR.md` and `docs/project-autopilot/TEST_REPORT.md`. No production data, payments, schema changes or deployment.

---

# Ramses Accounts G3N-S5 — SQLite/HTTP contention correction / TEST ONLY / NO-GO

New development branch `stabilization/s5-contention` from S4 `60bddc1`. Reproduced the S4 intermittent HTTP 500 as cross-thread `sqlite3.ProgrammingError` and the 10-second lock timeout as `OperationalError: database is locked` under extreme synthetic concurrency. Request-scoped SQLite connections now allow FastAPI worker-thread switching, and the single 30-second connection timeout governs database lock waits. Verified 384/384 HTTP writer requests with 48 workers after fix, 403 non-owner denial, SQLite integrity, matching audit and S4 integrated financial day (161 HTTP). Full 66-test CI run not completed under available execution time; eight focused regressions passed. No production deployment or genuine hospital acceptance. See `README_S5_AR.md` and `docs/project-autopilot/TEST_REPORT.md`.

---

# Ramses Accounts G3N-S4 - integrated financial day / TEST ONLY / NO-GO

Current development branch `stabilization/s4-integrated-day` from S3 `4e425e4`. One reusable synthetic single-DB acceptance test covers actual patient invoice and collection, 3 cashier shifts and internal vault, a prior closed-paper envelope, supplier procurement/settlement, separately authorized bank statement reconciliation, 2200 control, GL and guarded period close. It passes in FastAPI TestClient and over 161 HTTP requests to Uvicorn. Source full QA 141 = 135 PASS, 5 SKIP, 1 BLOCKED V8.0; CI 66/66 PASS. No production backend/GL/schema change or deployed system. One intermittent HTTP 500 under parallel test load is recorded for further investigation, **not considered repaired**. Read `README_S4.md` and `docs/project-autopilot/TEST_REPORT.md`. Production remains **NO-GO** until authentic historical migration, witness off-device restore, secured browser/LAN and authorized finance/clinical/IT UAT.

---

# Ramses Accounts V8.1E-G3N / S1 — Operational Stabilization / TEST ONLY

Latest UI/QA improvement: six task-specific warehouse workspaces replace the 23-panel mega-view; genuine Chromium-to-FastAPI TestClient-to-SQLite acceptance verifies synthetic independent receipt approval and Dr1100/Cr2200, but not network HTTP. **NO DB migration, new GL schema, bank action or production deployment.** Full regression 138 = 132 PASS/5 SKIP/1 BLOCKED V8.0/0 FAIL. Independent CI 66/66 PASS. See `README_S1_AR.md`, `STABILIZATION_S1_STATUS_AR.md`. **NO-GO hospital production.**

---

# Ramses Accounts V8.1E-G3N — Supplier Opening Statement Control / TEST ONLY

Latest development: signed-source-reference supplier prior-month-end statement comparison to posted GL 2200, source SHA-256, separate maker/checker, no GL/cash change. Details `README_G3N_AR.md`; production NO-GO.

- Latest full regression 138: **132 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT**, exit 0. Independent CI 66/66 PASS; 12/12 real Chromium UI flows PASS; delivery archive evidence is recorded separately.

---

# Ramses Accounts V8.1E-G3M — Evidence-based historical supplier AP attribution / TEST ONLY

- Based on verified G3L source commit `981f7adeff554707e3aa91792882b915f2631122`; branch `feat/g3m-supplier-attribution`.
- An original *posted, unlinked* manual GL journal with exactly one account-2200 line can be classified to a supplier only with evidence, justification and independent review. No journal, opening balance, tax, cash voucher, bank transfer, or financial amount is generated, updated, or deleted.
- SQL and API protect source eligibility, non-duplication, immutable proposal, grant revocation, independent checker (not original GL maker/reviewer), rejected proposal history and as-of temporal truth.
- `supplier_subledger.py` includes approved mapping only from its actual Cairo review date; older reports stay unattributed. G3L receipt, payment, reversal and anomaly handling stay intact.
- Cairo RTL UI shows original journal ID, signed 2200 amount, named supplier, proof and reason before approval. Owner and explicitly delegated warehouse operator prepare; reviewer with grant or independently authorized owner reviews, never original GL author/reviewer.
- Verified full local regression 136 scripts: 130 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT; independent CI 64/64 PASS; eleven Chromium browser flows pass at 320/375/1440. Original V8.0 migration remains BLOCKED, not passed.
- Production **NO-GO**: original V8.0, independent off-device recovery, finance evidence policy, signed bank beneficiary proof, real hospital UAT and medical/finance/IT signoff absent.

---

# Ramses Accounts V8.1E-G3L — Supplier 2200 Control Reconciliation / Cairo / TEST ONLY

- Built from verified G3K commit `5211e6a690ea15868b2f1748a55de5e35c2e3c0e` on separate `feat/g3l-supplier-control-ledger` branch.
- Read-only source-linked GL account 2200 reconciliation as-of a selected date, including **approved GRNs before supplier invoice match**, posted G3K bank payment and reversal journals, and explicit unmatched/unattributed entries. Vendor subtotal is not asserted to include all historical opening AP.
- Current inventory permission required for vendor names and document sources; dashboard uses Cairo RTL and a date-filtered reconciliation. No new schema, tax assumptions, VAT, adjustment GL or bank transfer.
- Production remains **NO-GO**: missing original V8.0 source archive, off-device restore, actual beneficiary evidence, accountant-approved adjustment policies, and medical/finance/IT signoff. See `README_G3L_AR.md` and `RAMSES_V81E_G3L_SUPPLIER_LEDGER_QA_AR.md`.

---

# Ramses Accounts V8.1E-G3K — Supplier AP Bank Voucher Link / Cairo / TEST ONLY

- Based on authenticated G3J commit `d26d77afdc139e444a0d55c30e2d423f2cec36a4`, branch `feat/g3k-supplier-ap-bank-link`; only synthetic test data.
- Pending bank voucher linked to independently approved G3J supplier request, bank fund grants, protected category, immutable SQL lineage and independent bank voucher reviewer. Approved voucher: Dr2200 / Cr Bank once, not inventory and not another supplier accrual. No bank transfer is initiated.
- Report separately identifies posted book vouchers, active bank statement matches, and signed-bank-statement with matching reference. Do not equate bank statement reference match to receipt by the named beneficiary.
- Retry rejected or reversed vouchers with auditable history, block generic reversal while a bank match remains active. Cairo RTL font remains nonblocking, with offline fallback.
- **Full source-owned regression: 133 tests = 127 PASS / 5 SKIP / 1 BLOCKED_NO_V80 / 0 FAIL / 0 TIMEOUT, exit 0.** Independent CI 61/61 PASS, Chromium 9/9 synthetic UI flows PASS at widths 320/375/1440.
- **NO-GO production** pending original V8.0 archive, actual bank beneficiary evidence, independent off-device restore, real hospital trial and medical/finance/IT signoff. See `README_G3K_AR.md`, `RAMSES_V81E_G3K_SUPPLIER_BANK_QA_AR.md`.

---

# Ramses Accounts V8.1E-G3J — Cairo / Supplier Pre-Payment Requests / TEST ONLY

- Development continues from genuine G3I Git history, isolated on `feat/g3j-cairo-payment-requests`. Synthetic data only; no production posting.
- Cairo Arabic variable typography (200–1000) across RTL UI and print with typography weights; nonblocking post-load Google Fonts CSS in restricted CSP, system fallbacks offline; no font binaries bundled.
- Independent pre-payment request authorization against approved supplier maturity installments; capacity guards, immutable evidence, SQL enforced independent reviewer; explicitly **NOT a bank payment, cashbook voucher, or reduction of account 2200**.
- Frozen authentic G3I schema migration tested with independently restored encrypted rollback. FINAL local 131 scripts: 125 PASS / 5 SKIP / 1 BLOCKED_NO_V80 / 0 FAIL; CI 59/59 PASS; nine Chromium flows PASS at 320/375/1440. See `README_G3J_AR.md`, `RAMSES_V81E_G3J_CAIRO_PAYMENT_QA_AR.md`.
- Production gate **NO-GO**: missing V8.0, off-device restore, bank evidence integration, UAT, medical/finance/IT approvals. Next G3K: actual supplier payment evidence/allocations with appropriate accounting rules and independent verification.

---

# Ramses Accounts V8.1E-G3I — Gross supplier maturity scheduling / TEST ONLY

- Restored and verified the original G3H source commit `b3cdcd2` and independently developed G3I on `feat/g3i-supplier-maturity` with only synthetic accounts, cases and invoices.
- One to 12 real-calendar installments per approved G3H invoice with exact piaster total, live independent approval, immutable SQL evidence and separate inventory month-close gate. No new payable ledger entries, cash vouchers or payments.
- RTL approval UI requires reviewer-visible amount/date for each installment. Supplier aging is explicitly **GROSS BEFORE PAYMENT**, never actual unpaid balance.
- Frozen authentic G3H schema SQL and independently locally restored encrypted pre-upgrade rollback. See `README_G3I_AR.md`, `RAMSES_V81E_G3I_SUPPLIER_DUE_QA_AR.md` for implementation and current independent QA results.
- **NO-GO:** missing original V8.0 archive, off-device recovery, real supplier/bank docs and approvals, medical/finance/IT UAT and hospital deployment authorization. Next: verified supplier payment allocation and debit/credit adjustment policy; no automated money movement.

---

# Ramses Accounts V8.1E-G3H — PO, partial GRN and invoice line-level matching / TEST ONLY

- Based on original G3G commit `4be7173`; isolated local development `feat/g3h-purchase-order-invoice-match`.
- Purchase order and signed reviewer do not post GL; GRN posts Dr1100/Cr2200 once, and the supplier invoice line-by-line match confirms evidence only. Separate reviewer and SQL guards prevent overreceipts, forged invoice totals, repeated item lines and closed-period edits.
- Historical unlinked receipts and existing accounting/clinical journals remain unchanged. Frozen original G3G SQL schema is migrated after authenticated encrypted backup, restored independently to a separate database in testing.
- **Final local QA:** 126 scripts = 120 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL (exit 0). Independent CI 54/54 PASS (exit 0); six Chromium flows G3H/G3G/G3F/G3D/G3B/G3A pass on 320/375/1440. Frozen G3G schema upgrade, encrypted rollback and independently verified restore pass locally. See `RAMSES_V81E_G3H_PURCHASE_QA_AR.md`; tests use synthetic data. **NO-GO hospital production**.

---

# Ramses Accounts V8.1E-G3G — Independent rejected-stock writeoffs (1 November 2026) / TEST ONLY

- Based on original G3F commit `0e87a3b` on `feat/g3g-return-writeoffs`. No production deployment, live hospital database, patient or payment mutation.
- New immutable partial writeoff for physically removed, medically rejected original FIFO return lines. An independent warehouse approver creates Dr5195/Cr1100 using historical lot cost; pending/rejected requests do not adjust stock or GL. Original RETURN Dr1100/Cr5100, FIFO issues, and case-cost history remain immutable.
- SQLite and API enforce active warehouse grants, proposer/reviewer separation, amount and cumulative quantity constraints, sealed-period checks, non-reissued historical lot validation, source GL verification and no month close with pending writeoff.
- Stock and reconciliation reports subtract approved writeoffs; RTL warehouse UI shows only stock line/batch, not patient or clinical notes. Frozen G3F SQL schema upgrade is preceded by encrypted, locally verified rollback.
- **Local G3G QA results:** see `RAMSES_V81E_G3G_WRITEOFF_QA_AR.md`; Full regression: 123 = 117 PASS + 5 SKIP + 1 BLOCKED_NO_V80, 0 FAIL, exit 0. CI 51/51 PASS; Chromium G3G/G3F/G3D/G3B/G3A 5/5 independent flows on 320/375/1440. Skips and block excluded from pass count.
- **NO-GO:** hospital disposal policy, physical witness signatures, off-device restore, V8.0 archive, medical/finance/IT UAT and approval still missing. Next: supplier purchase orders and 3-way match.

---

# V8.1E-G3F — Quarantined return / independent medical disposition (1 November 2026) / TEST ONLY

- Built on verified G3E source commit `827d458`, on isolated `feat/g3f-return-quarantine` branch. No production or patient databases used.
- The original independent financial return, Dr1100/Cr5100 and net case cost remain unchanged. All approved returned lot quantities stay medically quarantined until a department-granted, independently reviewed clinician approves release with documented inspection; reject remains quarantined until an independently posted loss adjustment (not yet implemented).
- FIFO API, direct SQLite allocation and final approval triggers now require released original returned lots by business date. Frozen G3E encrypted upgrade/independent local restore tests cover old used returned units and old pending preallocations; no false medical backfill.
- Stock UI separates owned / quarantined / nonquarantined, clinical queue omits patients/prices, and medical date uses Africa/Cairo in the browser.
- **Full regression 121 scripts: 115 PASS, 5 SKIP unavailable references, 1 BLOCKED original V8.0, 0 FAIL, exit 0. CI 49/49 PASS, exit 0.** Chromium G3F/G3D/G3A/G3B tests PASS at 320/375/1440. See `README_G3F_AR.md`, `RAMSES_V81E_G3F_QUARANTINE_QA_AR.md` and QA files.
- **NO-GO** pending hospital-approved reuse policy and infection control, validated clinician licensing, physical quarantine/disposal, on-site UAT, financial/medical/IT approvals, original V8.0 and off-device recovery.

---

# V8.1E-G3E — Case privacy for inventory issues / TEST ONLY (1 November 2026)

- Restored genuine G3D source, authenticated original ZIP/BUNDLE SHA-256, isolated local `feat/g3e-inventory-privacy` branch; no live deployment or clinical data.
- Inventory overview now limits patient-case issues/returns using the warehouse user's CURRENT billing-point access. Owner and unlinked warehouse documents remain accessible.
- Reviewer case-point access revalidated within transaction before approval/rejection and before disclosing decided document status; pending/rejected return submissions also check patient scope before status validation. Unauthorized approval posts no stock or GL.
- G3E test-first regression covers two distinct billing points, active grant revocation, owner visibility, unrelated-case denials and no unauthorized journal. Release label updated across HTTP, UI and Mac; independent QA skip classifier corrected to treat `SKIP:` as non-pass.
- Independent CI **47/47 PASS exit 0**, and synthetic Chromium returns UI at 1440/375/320 PASS; see `QA_G3E_CI_RESULTS.txt`, `QA_G3E_CHROMIUM_RESULTS.txt`.
- Full local regression after the final code change: **119 scripts: 113 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL**, exit 0. See `QA_G3E_TEST_RESULTS.tsv` and `RAMSES_V81E_G3E_PRIVACY_QA_AR.md`. **NO-GO production** pending physical quarantine/clinical safety, original V8.0, off-device restore, real hospital UAT and financial/medical/IT signoff.

---

# V8.1E-G3D — Original-lot consumables returns / TEST ONLY (1 November 2026)

- Local isolated branch `feat/g3d-case-consumables-returns` based on verified G3C commit `2a5d2ee`; synthetic data only, no hospital deployment.
- Independently approved non-drug FIFO returns from original issue allocations, preserving original issues and journals; Dr1100/Cr5100 separate reviewed return journal and net case-consumables reports.
- SQLite/API enforced quantity, expiry, current case grant, historical FIFO date, month close and pending-return case-close guards. Unapproved returns do not change financial balances.
- Frozen G3C schema upgrade behind authenticated encrypted `.rbe` rollback, isolated restore test; original historical rows not backfilled or altered.
- QA final regression: 120 scripts = 114 PASS / 5 SKIP unavailable historical source / 1 BLOCKED_NO_V80 / 0 FAIL; independent CI 45/45 PASS exit 0; archive verification is recorded separately. See `RAMSES_V81E_G3D_RETURN_QA_AR.md` and downloadable QA reports.
- NO-GO production: medical sterilization/quarantine policy, on-site UAT, real V8.0 archive, independent offsite backup restoration, chief accountant and medical/IT signoff missing.

---

# V8.1E-G3C — Case consumables FIFO cost / TEST ONLY (31 October 2026)

- Isolated branch `feat/g3c-case-consumables-cost` based on verified G3B commit `4933339`; no production hospital financial/patient data, no deployment.
- Double-authorized read-only per-case approved inventory cost (warehouse and billing-point grant), with explicit pending/unlinked exclusions; responsive inventory search UI.
- New approval-order guard for FIFO across different business dates in API and SQLite. No retroactive approved journal/stock mutation and no auto financial correction.
- Additive SQLite triggers with verified encrypted `.rbe` rollback before G3B upgrade; frozen original G3B schema fixture.
- QA: 116 scripts = 110 PASS / 5 SKIP / 1 BLOCKED_NO_V80 / 0 FAIL; CI 42/42 PASS. Evidence in `RAMSES_V81E_G3C_CASE_COST_FIFO_QA_AR.md`, `README_G3C_AR.md` and QA files. Production **NO-GO** unchanged.

---

# V8.1E-G3B — Source document fingerprint (31 أكتوبر 2026) / TEST ONLY

- **Local source**: `feat/g3b-clinical-document-fingerprint`, created from verified G3A source commit `885e80e`; no deployment, financial posting or real hospital accounts modified.
- Clinician-only synthetic PDF/JPG/PNG upload creates SHA-256/size/media metadata bound to immutable service attestation. Source file contents and original filenames are not persisted in finance database or audit log; system/Starlette may spool uploads into temporary files, which needs encrypted host storage and privacy review before any genuine use.
- Owner may opt in one department to an immutable mandatory-document policy with password re-entry and pre-existing unbilled-witness guard. Invoice finalization and direct SQLite attestation reject un-hashed proof when required. Source re-upload verification honors current department grant.
- Real frozen G3A schema upgrade: authenticated `.rbe` pre-DDL rollback, isolated restoration, no historical witness backfill; responsive Chromium at 320/375/1440.
- **G3B full regression:** 112 executed scripts = **106 PASS / 5 SKIP / 1 BLOCKED original V8.0 / 0 FAIL / 0 TIMEOUT**. Original automated report mistakenly labeled 3 historical scripts PASS because they print `SKIP ` without colon; reclassified against captured stdout and individually rechecked. CI separately 39/39 PASS, 3 Chromium scripts PASS; source-archive validation recorded in final G3B artifact.
- **NO-GO** until independent medical credential approval, legal signature/document custody/IT security, off-device restore, original V8.0 and prior source fixtures, approved remediation for old witness, full hospital/UAT and financial signoff. See `RAMSES_V81E_G3B_DOCUMENT_FINGERPRINT_QA_AR.md` and `README_G3B_AR.md`.

---
# V8.1E-G3A — Clinician Role Isolation (31 أكتوبر 2026) / TEST ONLY

- **مرجع المصدر:** إصدار G2Z الموثّق commit `a17aeec`؛ فرع اختبار محلي `feat/g3a-clinician-isolated-access`، لا نشر ولا وصول لأي قاعدة مستشفى حقيقية.
- **الهوية الطبية المستقلة:** دور `clinician` منع افتراضيًا من جميع مسارات المحاسبة والصندوق والمرضى والرواتب والقيود والتقارير؛ يمتلك فقط طابور إثبات خدمات القسم المفوض ومرجع إثباته وجلسة الدخول/الخروج.
- **المراجعة المهنية التجريبية:** يقرّها المالك بعد إدخال كلمة مروره مجددًا؛ معلومة داخلية ولا تعني ترخيصًا رسميًا أو توقيعًا إلكترونيًا أو اعتماد مدير طبي مستقل.
- **دورة الحساب:** إعادة تعيين كلمة مرور الطبيب أو تعطيله تلغي الموافقة الطبية؛ إعادة التفعيل تستلزم مراجعة جديدة. لا تُحذف التوقيعات التاريخية.
- **الترحيل:** أصل G2Z SQLite محفوظ كـfixture صناعية؛ تتم نسخة تراجع مشفرة قبل إعادة بناء جدول المستخدمين، مع الاحتفاظ بأرقام المستخدمين والجلسات والمراجع التاريخية وفحص العلاقات؛ تسحب منح المشاهد التجريبية القديمة ولا تحوّلها إلى هويات طبية.
- **حماية تاريخ G2Z:** إثبات `viewer` القديم يبقى لسجل التدقيق فقط ولا يكفي لفاتورة جديدة لقسم محمي؛ الحالات القديمة غير المفوترة تحتاج قرار تسوية طبي ومالي مستقل.
- **واجهة RTL:** شاشة الطبيب التجريبية 320/375/1440، شاشة مراجعة المالك 375/1440؛ إصلاح تمرير قائمة الإدارة على الموبايل؛ اختبارات Chromium ببيانات وواجهات API وهمية.
- **الاختبار الشامل النهائي:** 109 سكربتًا = **103 PASS، 3 SKIP مصادر G2J/G2K/G2L، 2 SKIP ملف Excel خاص، 1 BLOCKED أرشيف V8.0 الأصلي**؛ **0 FAIL**. `QA_G3A_TEST_RESULTS.tsv`.
- **الاختبارات الإضافية:** 37/37 PASS في تشغيل منفصل (31 أكتوبر 2026)؛ لا تعوض اختبارات المصدر التاريخي/القبول السريري/التشغيل الميداني. `QA_G3A_CI_RESULTS.txt`.
- **NO-GO للإنتاج:** اعتماد ترخيص الطبيب وفصل الإدارة الطبية عن المالية، نسخة الاستعادة خارج الجهاز، أرشيف V8.0، موافقات المسؤولين الثلاثة (الطبي/المالي/IT) واختبار UAT، تسوية الإثباتات القديمة غير المفوترة، إكمال صلاحيات السجلات والمشتريات/الأطباء/التأمين.

---
# V8.1E-G2Z — Independent Clinical Attestation Pilot (31 أكتوبر 2026) / TEST ONLY

- **Local development branch:** `fix/g2z-clinical-evidence-gate`, derived from verified G2Y commit `405974d`.
- Department-level pilot clinical sign-off backed by active owner grant to `viewer`-class synthetic account; never a substitute for medical identity/credential verification.
- Finance cannot independently fulfill protected clinical services; invoices and drafts require independent evidence after owner activation, including recheck of old drafts.
- Immutable SQL attestation rows and active-policy check; no fake historical signatures. Frozen G2Y encrypted migration with isolated restore tested.
- Chromium pilot UI at 320/375/1440 tested with stubbed synthetic network. Full suite: 101 PASS, 5 SKIP, 1 blocked missing V8.0 / 107, zero functional failures; CI smoke 35/35 PASS. Evidence in `QA_G2Z_TEST_RESULTS.tsv` and `QA_G2Z_CI_RESULTS.txt`.
- **NO-GO:** clinical/legal sign-off, full medical identity, financial governance, offsite backup, original V8.0 archive, hospital UAT and deployment approvals are missing.

---

- **بوابة CI المحلية النهائية: 33/33 PASS**؛ الاختبارات التاريخية الناقصة ليست جزءًا من البوابة. النتيجة `QA_G2Y_CI_RESULTS.txt`.
## V8.1E-G2Y — Project Autopilot (31 أكتوبر 2026) / TEST ONLY

- آخر مصدر: فرع محلي `fix/g2y-financial-report-scope`، مبني على G2X commit `a4042c3` دون أي اتصال إنتاجي.
- تقارير `/api/reports` النقدية تُفلتر حسب صلاحيات الصناديق الحالية **قبل التجميع**؛ المشاهد يرى النقدية المسموحة فقط، من دون إجماليات GL/الرواتب، والمراجع يُحجب عنه هامش النقدية المقيدة مقابل الرواتب العامة.
- منع دور `viewer` من مطابقة حسابات المرضى الشاملة، وفصل رابط المطابقة الكلية للخزن الذي يملكه `owner` وحده؛ إصلاح تسريب شاشة مالك سابق عند تبديل حساب المستخدم بنفس المتصفح.
- اختبار TDD عبر FastAPI/SQLite بكلمات مرور وقيم وهمية؛ Chromium 375px و1440px؛ إلغاء ومنح إذن ثم إلغاء؛ عدم تغيير أي بيانات حسابات حقيقية.
- **الانحدار الشامل الجديد: 105 اختبارًا = 99 PASS و3 SKIP مصدر تاريخي و2 SKIP ملف مرجعي خاص و1 BLOCKED_V8.0، بلا إخفاق وظيفي**. راجع `QA_G2Y_TEST_RESULTS.tsv`، وملف تقرير G2Y.
- بوابة CI المحلية: افحص `QA_G2Y_CI_RESULTS.txt` عند صدور نتيجة التشغيل النهائي؛ لا تُخلط نتيجتها بنتائج G2X.
- ما زال NO-GO: اعتماد رئيس حسابات لنطاق GL والمراجع، إقرار تنفيذ الخدمة الطبي، الاستعادة الفعلية خارج الجهاز، أرشيف V8.0، أتمتة المستحقات والمشتريات والأطباء والتأمين، UAT وموافقة المالية والطبي وIT.

---

# Ramses Accounts V8.1E-G2X — Restricted cashier shift privacy / TEST ONLY (31 Oct 2026)

**Current isolated development branch:** `fix/g2x-restricted-shift-authorization` starting from G2W commit `35f22cd`. This is local source only; **NO-GO** for real patient or financial processing.

- Reuses current `user_fund_grants`: ungranted reviewers cannot read restricted cash/bank/wallet cashier shifts, their attachments, variance details, station schedules and day totals. Object-level decisions require `can_approve` for a restricted fund. Grant revocation takes effect on the next request.
- Retains G2W viewer denial on global journal/trial balance JSON and CSV. Updates a stale legacy test that still expected unrestricted viewer access; restores G2X version identity in HTTP, UI and Mac launcher.
- No schema or money-posting algorithm changes; only restricted-reader/reviewer authorization and release labels.
- Automated endpoint inventory is a heuristic worklist, not independent approval of all routes.
- QA recheck: 104 scripts, 98 PASS, 3 historical SKIP, 2 private-workbook SKIP, 1 blocked original V8.0, 0 FAIL. CI smoke 32/32 PASS. One preview HTTP failure in the preceding run did not recur in standalone or full recheck; root cause still unknown.
- See `RAMSES_V81E_G2X_PERMISSION_QA_AR.md`, `QA_G2X_TEST_RESULTS.tsv`, `README_G2X_AR.md`, and source-history Git Bundle.
- Remaining hard blocks: independently approved reporting hierarchy, clinician-signed service attestations, offline/offsite restore, V8.0 source, procurement/doctor/insurance lifecycle and hospital acceptance.

---

# Ramses Accounts V8.1E-G2V — Encrypted upgrade rollback / TEST ONLY (31 Oct 2026)

**Current local development branch:** `fix/g2v-encrypted-upgrade`; derived from G2U. **NO-GO** for patient or monetary production use. No deployment or connection to hospital database.

- Encryption before schema upgrade: existing older or partially upgraded SQLite databases require an authenticated `.rbe` preflight archive; no secure key means the DDL operation stops without altering historic records.
- Destructive shift-table migration creates an independent encrypted `.rbe` rollback, not a persistent plaintext SQLite file.
- Uses established AES-256-GCM/scrypt G2M backup tooling, with isolated authenticated restore; no silent downgrade or overwrite.
- Only synthetic historical and frozen G2T schema scenarios verified. Fresh G2V QA: 97 PASS / 3 SKIP / 1 BLOCKED V8.0 (101 scripts, 0 functional FAIL); CI smoke 29/29 PASS locally. See QA_G2V_TEST_RESULTS.tsv / QA_G2V_CI_RESULTS.txt.
- Transient sensitive SQLite snapshots may touch local disk during creation; use full-disk encryption in real operation. Existing plaintext pre-upgrade backups remain on user devices until inventoried and safely handled by IT.
- Still NO-GO: signed clinical attestation, full finance/HR report permissions, real offsite restore/UAT, missing V8.0 source, supplier/doctor/insurance subledgers and approved month close.

**G2V references:** `RAMSES_V81E_G2V_ENCRYPTED_UPGRADE_QA_AR.md`, `README_G2V_AR.md`, `RAMSES_G2V_FINDINGS_TRACKER.json`.

---
# Ramses Accounts V8.1E-G2U — Stabilization / TEST ONLY (31 Oct 2026)

**Current development source:** G2U is an additive fix based on the exact G2T source archive. **NO-GO for patient or monetary production use; no deployment.**

- Accounting: bed-night service date and fee period no longer follow admission month; current-period draft/invoice/GL and current-period close preflight are checked with isolated FastAPI+SQLite. Approved G2B historical catch-up retains original price/date and books GL only now.
- Database: additive `billing_case_lines.service_date`; a fulfilled record is immutable (UPDATE/DELETE blocked) without silently backdating legacy facts. Genuine frozen G2T schema initialized twice, preserved old draft and financial period attribution.
- Privacy: staff, fund balance and reviewer bank queue protections plus protected voucher lists, export, dashboard and attachment read gates; current fund grant revocation takes effect immediately. Still NOT a full RBAC audit.
- Evidence: `RAMSES_V81E_G2U_STABILIZATION_QA_AR.md`, `QA_G2U_TEST_RESULTS.tsv` (96 PASS, 3 SKIP, 1 BLOCKED/100; no functional FAIL), `QA_G2U_CI_RESULTS.txt` (28/28 PASS), `tests/test_v82_g2u_*.py`. Historical V8.0 migration needs the genuine archive and remains blocked.
- Unresolved P0: independent clinical attestation; unresolved P1: plaintext pre-upgrade SQLite rollback copies, broad reporting authorization and payment evidence defaults.

---
# Ramses Accounts V8.1E-G2T — Development / TEST ONLY

**Current tested source:** G2T based on frozen G2S; no live installation. New central non-drug inventory supplier receipt and FIFO issue with independent approval and linked balanced GL. See `RAMSES_V81E_G2T_INVENTORY_QA_AR.md`. Tests: 93/97 PASS, 3 historical SKIP, 1 blocked V8.0; CI smoke 25/25 PASS locally (separate run). No producer supplier settlement or pharmacy, **NO GO**.

---
# Ramses Accounts V8.1E-G2S — Development and testing only

## G2S — Project Autopilot M4b (2026-10-31)

- Based on frozen G2R ZIP; new `bed_transfers` immutably links atomic old and new physical stays with one owner-authorized dated transfer document; retry-safe, no financial journal or clinical discharge.
- Month-close now evaluates bed nights by **night_date** even for patients admitted in a previous month. Missing nights and unposted/uninvoiced nights block closure, including closed-period SQLite guards.
- SQL refuses a stale price version when a later tariff was effective at night date. Both transfer and latest tariff requirements have negative regression tests.
- A deliberately excluded private June Excel workbook is not fabricated. `--archive` fails closed; two historical-preview tests will SKIP when the fixture is absent.
- Frozen original G2R SQL schema migration verified twice. See `RAMSES_V81E_G2S_TRANSFERS_QA.md` and `QA_G2S_TEST_RESULTS.tsv`.
- **NO GO for production**: tariffs/month-end accounting and clinical transfer custody await approval. M4c/M6/M5/M7 remain open.

---
# Source release ledger — G2R (31 October 2026)

**Current development release: V8.1E-G2R.** Frozen G2Q source remains the upgrade baseline. No deployment or real financial data.

# V8.1E-G2R — Project Autopilot M4 / bed occupancy and priced nightly orders (31 Oct 2026)

Development-only addition based on **G2Q**; neither installed in hospital nor approved for live patient/payment use.

- New `bed_stays.py` + `schema.sql` structures for inpatient/NICU beds, period-scoped occupancy and immutable nightly service snapshots.
- Owner creates beds and records administrative admission/release only with evidence; cashier/reviewer read solely their authorized patient cases. No clinical discharge approval is represented.
- Date-effective room tariffs reuse the existing service price table; preview shows calendar nights **[start_date,end_date)**. This is a **provisional proposed rule**, NOT approved hospital billing policy; accountant and medical operations must confirm nights, partial days, transfers, payer, exemptions and month-end allocations.
- The owner explicitly orders missing nights as **billing_case_lines in ordered state**. Separate service fulfillment and invoice issuance remain necessary; no cash or GL posted when recording a bed or selecting nights.
- Concurrency constraints and SQL triggers prevent double occupancy, duplicate nights, cross-case snapshot links, unauthorized mutation of night evidence and re-opening financial cases. Financial case clearance blocks open bed stays and unrecorded nights. Same-day zero-night cancellation can still undergo independent no-charge review without fake invoices.
- NICU added as an additive seeded department; existing department IDs and historical records untouched.
- New regression tests: `test_v82_g2r_bed_stays.py`, `test_v82_g2r_bed_stays_ui.py`, `test_v82_g2r_upgrade.py` with frozen G2Q original schema. Test evidence: `QA_G2R_TEST_RESULTS.tsv` in release.

Next work: clinical custody/fulfillment role, signed tariff/partial-day policy, shift/transfer boundaries and long-stay month end; operations/NICU consumables -> inventory/procurement/suppliers -> doctors' fees. Non-production release gate remains **NO-GO**.

---
# Ramses Accounts — source release ledger (31 October 2026)

**Current source:** `V8.1E-G2Q` — Project Autopilot security-foundation increment based on G2P.
**Environment:** local source archive only. DEVELOPMENT / TEST ONLY — **NO-GO for real money or patient data.**

## Implemented (synthetic-data verified)
- F-012: `login_rate_events` per observed socket source and username; separate 40/15-minute per-source cap; failures only, owner on another source not locked out.
- F-013: employee directory hidden from clerk and viewer in `/api/lookups`; owner/reviewer retain payroll review directory.
- F-015: `backup.py` and systemd-compatible `backup_local.sh` now use authenticated encrypted `.rbe` backups or fail closed.
- F-016: SQL triggers deny update/delete of `audit_log` in an ordinary connected SQLite session.
- F-014 (partial): non-demo Google Sheets mirror now requires explicit privacy approval before any remote request; free preview remains bound to isolated synthetic staging sheet.
- F-026: keyboard skip navigation to main content, verified with offline Chromium at 375px.
- G2P -> G2Q genuine frozen-schema fixture tested twice with preserved records.
- M0: local CI smoke command `python3 scripts/ci_smoke.py` and GitHub Actions workflow authored **but remote CI not yet executed**.

## Constraints
- Auth source address depends on trusted ASGI proxy configuration; remote distributed abuse and shared-network throttling require additional controls/MFA.
- SQL triggers do not stop privileged SQLite file owners from tampering; independently stored append-only audit trails required.
- Existing plaintext backups require inventory/secure treatment; script change does not encrypt old files or set up off-device storage.
- Live Git repository/CI, V8.0 migration fixture, real browsers/devices and accountants' production sign-off remain unverified.
- Missing hospital modules: bed occupancy, operations/NICU costing, procurement/inventory/suppliers, physician fees, annual close, full RBAC.

**Evidence:** `RAMSES_V81E_G2Q_AUTOPILOT_QA_AR.md`, `QA_G2Q_TEST_RESULTS.tsv` and the 32-item register updated as `RAMSES_G2Q_FINDINGS_REGISTER.json`.

- **G3L final broad-regression evidence**: 134 scripts = 128 PASS / 5 SKIP / 1 historical V8.0 BLOCKED / 0 FAIL / 0 TIMEOUT (exit 0). Ten independent Chromium GUI flows PASS at 320/375/1440. Source-owned CI 62/62 PASS (exit 0); independent extracted-artifact verification recorded separately after packaging; no production deployment.
