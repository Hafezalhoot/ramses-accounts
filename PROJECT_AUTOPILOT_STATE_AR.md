- G2Y CI محلي: **33/33 PASS**؛ الانحدار الشامل 99/105 مع 5 SKIP و1 BLOCKED؛ التشغيل الحقيقي NO-GO.
## V8.1E-G2Y — Project Autopilot (31 أكتوبر 2026) / TEST ONLY

- آخر مصدر: فرع محلي `fix/g2y-financial-report-scope`، مبني على G2X commit `a4042c3` دون أي اتصال إنتاجي.
- تقارير `/api/reports` النقدية تُفلتر حسب صلاحيات الصناديق الحالية **قبل التجميع**؛ المشاهد يرى النقدية المسموحة فقط، من دون إجماليات GL/الرواتب، والمراجع يُحجب عنه هامش النقدية المقيدة مقابل الرواتب العامة.
- منع دور `viewer` من مطابقة حسابات المرضى الشاملة، وفصل رابط المطابقة الكلية للخزن الذي يملكه `owner` وحده؛ إصلاح تسريب شاشة مالك سابق عند تبديل حساب المستخدم بنفس المتصفح.
- اختبار TDD عبر FastAPI/SQLite بكلمات مرور وقيم وهمية؛ Chromium 375px و1440px؛ إلغاء ومنح إذن ثم إلغاء؛ عدم تغيير أي بيانات حسابات حقيقية.
- **الانحدار الشامل الجديد: 105 اختبارًا = 99 PASS و3 SKIP مصدر تاريخي و2 SKIP ملف مرجعي خاص و1 BLOCKED_V8.0، بلا إخفاق وظيفي**. راجع `QA_G2Y_TEST_RESULTS.tsv`، وملف تقرير G2Y.
- بوابة CI المحلية: افحص `QA_G2Y_CI_RESULTS.txt` عند صدور نتيجة التشغيل النهائي؛ لا تُخلط نتيجتها بنتائج G2X.
- ما زال NO-GO: اعتماد رئيس حسابات لنطاق GL والمراجع، إقرار تنفيذ الخدمة الطبي، الاستعادة الفعلية خارج الجهاز، أرشيف V8.0، أتمتة المستحقات والمشتريات والأطباء والتأمين، UAT وموافقة المالية والطبي وIT.

---

# Project Autopilot — G2X (31 أكتوبر 2026)

- **المصدر:** فرع تطوير معزول `fix/g2x-restricted-shift-authorization` مبني على Git G2W `35f22cd`، بدون نشر أو تعديل حسابات حقيقية. **NO-GO**.
- **المهمة:** منع مراجع بلا تفويض نشط من قراءة كشف/مرفق/ملخص أو اتخاذ قرار في وردية خزنة مقيدة، مع عدم المساس بالوردية العامة وصلاحية المالك؛ قرار اعتماد الجرد يتطلب `can_approve`.
- **الدليل:** اختبار HTTP على SQLite تجريبية فشل على أصل G2W بإظهار وردية مقيدة، ثم نجح بعد الإصلاح مع منح/سحب حي وتفريق حق الاطلاع وحق الاعتماد.
- **الاختبارات:** إعادة نهائية 104: 98 PASS، 3 SKIP تاريخي، 2 SKIP ملف خاص، 1 BLOCKED V8.0، 0 FAIL؛ وبوابة CI = 32/32 PASS. تعطل اختبار معاينة HTTP أول مرة ثم نجح منفردًا وفي الإعادة، والسبب غير محسوم.
- **متابعة مراجعة المسارات:** ملف CSV يغطي 181 route آليًا ويحدد الحالات المشتبه بحساسيتها، لكنه ليس تصنيفًا أمنيًا نهائيًا.
- **أول 3 خطوات تالية:** (1) اعتماد صلاحيات التقارير المجمعة والأستاذ العام وكشوف الموظفين، (2) فصل توثيق تنفيذ الخدمة طبيًا عن إصدار الفاتورة، (3) استكمال الموردين والمشتريات والاستحقاقات وربط دفتر الأستاذ.

---

# Project Autopilot — مرحلة G2V (31 أكتوبر 2026)

- **آخر سورس محلي:** G2U بعد تعديلات G2V على الفرع `fix/g2v-encrypted-upgrade`، من غير نشر أو تعديل قاعدة بيانات المستشفى. **NO-GO** للإنتاج.
- **M1 / G2T-N05:** إصلاح تشفير كل نسخ التراجع التي ينشئها مسار الترقية، بما فيها ترحيل جدول الورديات؛ المفتاح المفقود أو ملف مفتاح بصلاحيات مكشوفة يؤدي لإيقاف الترقية قبل تعديل الـSQL.
- **M0:** اختبار استعادة صورة تاريخية (V7.8) ومخطط G2T المجمد وترقية جزئية، على بيانات وهمية. المفاتيح لا تُضمّن في الحزمة ولا في السورس.
- **نتائج الجولة:** **101 اختبارًا: 97 PASS، 3 SKIP، 1 BLOCKED V8.0، بدون إخفاق وظيفي؛ CI المحلي 29/29 PASS.** سجل النتائج G2V مستقل عن G2U؛ اختبار V8.0 الأصلي غير متاح.
- **موانع ومخاطر:** ملفات نسخ سابقة غير مشفرة تحتاج جردًا، تخزين مؤقت على القرص يستوجب تشفير الجهاز، استعادة خارج الجهاز على أجهزة رمسيس وموافقة IT؛ اعتماد سريري وصلاحيات شاملة وتمويل/موردين ومخازن وأطباء وتأمين وتقارير ما زالوا ناقصين.
- **أول 3 مهام تالية:** 1) مصفوفة شاملة لصلاحيات القراءة/التصدير، 2) فصل اعتماد الخدمة الطبية عن المالية، 3) مستندات الموردين واستحقاقاتهم وربطها بالأستاذ.

---
# حالة Project Autopilot — G2U بعد تدقيق G2T (31 أكتوبر 2026)

- **الحالة: تطوير محلي لا إنتاج. NO-GO.** أصل السورس هو G2T الموثق ببصمة SHA-256؛ الفرع المحلي `fix/g2u-cross-month-billing`، ولم يحدث Push/Deploy.
- **Sprint 0 / G2T-N01+N07:** فوترنا في اختبار تلقائي ليلة أكتوبر ضمن حالة سبتمبر المقفل، وقيدنا في أكتوبر، وصححنا تأريخ خدمات السرير وفحص إقفال الشهر وغطاء الأستاذ، مع احترام مسار G2B التاريخي المعتمد.
- **Sprint 1 / G2T-N02+N03+N04 جزئي:** منع مشاهد من كشف الموظفين والأرصدة، وفلترة حسابات البنك والاعتمادات والتصدير والمرفقات ولوحة الحسابات حسب تفويض حي، مع اختبار سحب تفويض أثناء الجلسة. باقي المسارات تستلزم مراجعة وصلاحيات مرجعية معتمدة.
- **M0:** ترقية G2T→G2U إضافية صامتة عن بيانات المرضى: حفظ تاريخ خدمة قديم غير موثق NULL، سعر وسندات قديمة كما هي، مع منع تغيير مستند تنفيذ مؤكد. إعادة تهيئة على مخطط G2T الأصلي مرتين نجحت. **التغطية الحالية 100 اختبار: 96 ناجح، 3 SKIP، 1 محجوب V8.0. CI سريع 28/28 ناجح**. نسخة V8.0 الأصلية ما زالت غائبة.
- **المرجع التفصيلي:** `RAMSES_V81E_G2U_STABILIZATION_QA_AR.md`، وسجل اختبارات `QA_G2U_TEST_RESULTS.tsv`.
- **التالي:** تشفير كل نسخ التراجع قبل الترقية، مصفوفة قراءة جميع API، إثبات طبي مستقل، ثم الموردون والمخازن والأطباء/التأمين/الإقفال. لا ترفع بيانات حقيقية قبل تجربة ميدانية وموافقات مالية وطبية وتقنية.

---
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
