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
