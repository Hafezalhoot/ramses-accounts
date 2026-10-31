# حالة Project Autopilot — بعد G2T

- المصدر الحالي: **V8.1E-G2T**؛ ملف ZIP تجريبي، بدون نشر على سيرفر المستشفى.
- **M6a: مختبر محليًا**: مخزن مركزي مستلزمات غير دوائية، استلام موردين موثق، صرف FIFO بالأقسام والحالات المسموح بها، قيود محاسبية عند الاعتماد ومطابقة محدودة المصدر.
- أصلحنا اختلاف إصدار الخادم/مشغّل الماك، وسباق سحب تفويض المخزن خلال الاعتماد داخل المعاملة.
- نتائج مسجلة: **93 PASS، 3 SKIP، اختبار V8.0 محجوب**؛ و**25/25 اختبارات CI سريعة** في تشغيل منفصل.
- موانع التشغيل: موردون/مدفوعات/أوامر شراء/جرد متعدد/أدوية ومستهلكات العمليات، صلاحيات المستشفى الشاملة، UAT واستعادة خارج الموقع، اعتماد سياسة التسعير والضرائب.
- الأولويات الثلاث القادمة: (1) موردون وفواتير/مردودات وسداد محكوم، (2) مخازن متعددة وربط تكلفة الحالات، (3) اختبارات تشغيل وأمان واستعادة فعلية.
- ملفات الحالة: `RAMSES_V81E_G2T_INVENTORY_QA_AR.md` و`QA_G2T_TEST_RESULTS.tsv` و`QA_G2T_CI_25_TEST_RESULTS.tsv`.

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
# Ramses Project Autopilot — state after G2R

- Base: G2Q frozen source ZIP. G2R extends `schema.sql` additively, `bed_stays.py`, `case_settlement.py`, `bootstrap.py`, `app.py`, `static/billing.js`, tests and trial labels.
- M0/M1/M2: partial; repository/CI not deployed, comprehensive privileges and audit external anchoring remain open.
- M4: **in progress**. Bed master, administrative occupancy intervals, date-effective quote, explicit ordered nights, SQL collision/immutability and patient case clearance gates **tested locally**. No approved bed tariff policy, medical discharge module or actual operating day-based invoice accrual.
- M3: cashier/GL/POS still trial; M5-M8: inventory/suppliers, OR/NICU consumables and doctor fees remain unimplemented.
- Test detail: `QA_G2R_TEST_RESULTS.tsv` and `RAMSES_V81E_G2R_BEDS_QA_AR.md`.
- Genuine old V8.0 ZIP missing: historical upgrade test cannot pass; do not fabricate an archive.
- NO GO for production. No deployment, no live bank connections, no hospital data. Safe next 3 slices: (1) clinical service verification and sign-off for tariffs; (2) bed transfer/long admission accrual across month close; (3) inventory receipts/issues and patient costing with subledger.
