# Ramses Accounts V8.1E-G2S — Development and testing only

## G2S — Project Autopilot M4b (2026-10-31)

- Based on frozen G2R ZIP; new `bed_transfers` immutably links atomic old and new physical stays with one owner-authorized dated transfer document; retry-safe, no financial journal or clinical discharge.
- Month-close now evaluates bed nights by **night_date** even for patients admitted in a previous month. Missing nights and unposted/uninvoiced nights block closure, including closed-period SQLite guards.
- SQL refuses a stale price version when a later tariff was effective at night date. Both transfer and latest tariff requirements have negative regression tests.
- A deliberately excluded private June Excel workbook is not fabricated. `--archive` fails closed; two historical-preview tests will SKIP when the fixture is absent.
- Frozen original G2R SQL schema migration verified twice. See `RAMSES_V81E_G2S_TRANSFERS_QA.md` and `QA_G2S_TEST_RESULTS.tsv`.
- **NO GO for production**: tariffs/month-end accounting and clinical transfer custody await approval. M4c/M6/M5/M7 remain open.

---
# بوابة الإصدار G2R — 31 أكتوبر 2026 — NO GO للتشغيل الحقيقي

- إشغال الأسرة وتسعير ليالٍ بالتاريخ أضيف للتجربة وربط بمسار خدمات المريض، مع قيود منع التكرار؛ **لم تعتمد المستشفى سياسة احتساب الليالي أو إشغال الأسرة سريريًا بعد**.
- لا ترحيل إيراد أو تحصيل بمجرد حجز السرير؛ لا بد من إثبات الخدمة والفاتورة والتحصيل العادي.
- لا يزال مخزون العمليات والحضانة والموردون والأطباء والصلاحيات والتشغيل متعدد الأجهزة وأرشيف V8.0 التاريخي غير مكتمل.
- هذا إصدار مصدر محلي للاختبار فقط ولا يجوز إدخال بيانات مرضى حقيقية أو إجراء تسويات أموال حقيقية به.

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
# بوابة إصدار G2Q — 31 أكتوبر 2026 — NO-GO للاستخدام الحقيقي

- اختبارات أمنية جديدة: `tests/test_v82_g2q_security.py`؛ دخول المصادر المختلفة، دليل الموظفين، سجل التدقيق غير القابل للتعديل، النسخ المشفر فقط.
- تصدير Google Sheets الحساس محظور افتراضيًا إلا بعد تفويض موثق وضبط متغير الموافقة؛ الاختبارات التجريبية فقط لا تمثل موافقة المؤسسة.
- أضيف GitHub Actions smoke workflow للمصدر، **ولم يتم تشغيله على GitHub ولم يُنشأ مستودع عن بُعد**.
- حظر التشغيل الحقيقي مستمر: وحدات تكلفة الداخلي والعمليات والحضانة والمخزون والموردين والأطباء، صلاحيات شاملة، نسخة خارج الجهاز، اختبار V8.0، مطابقة مالية كاملة، وUAT مستقل.
- حماية سجلات audit عبر trigger حماية لتطبيق SQLite العادي، وليست بديلًا عن سجل خارجي مضاد للعبث. كما أن الحد حسب عنوان المصدر ليس بديلًا عن MFA أو مراقبة التوزيع خلف proxy.

# بوابة الإصدار V8.1E-G2P — 31 أكتوبر 2026 — NO GO

- [x] قفل مالي لحالات الداخلي والحضانة والعمليات فقط مع مراجع مستقل وإعادة فحص الديون والخدمات والمقدمات لحظة القرار، دون خلق قبض/قيد جديد.
- [x] إلغاء حالات بلا أي خدمات أو فواتير أو تحصيل بموافقة مستقلة، ومنع تكرار القيد أو الإغلاق.
- [x] حماية DB بعد الإغلاق من التعديل والإضافة والحذف، واختبارات تزامن ومراجعة وصلاحيات.
- [x] 76 ملف اختبار: 72 PASS، 3 SKIPPED، 1 BLOCKED (ملف V8.0 التاريخي غير متوفر). واجهة Chromium على 1440/375/320 معزولة عن API الحقيقي.
- [ ] تنفيذ دورة الإقامة/السرير/العمليات/الحضانة الفعلية وتكاليفها، ومخازن/موردين/أطباء، وتصحيح بعد الإغلاق، وRBAC شامل.
- [ ] الاختبار على أجهزة المستشفى، مطابقة حسابات حقيقية، اعتماد محاسبي وأمني، نسخ احتياطية خارج الموقع واسترجاع كامل، وإتمام اختبارات الترقية التاريخية.

**لا نشر ولا بيانات مرضى أو نقدية حقيقية.** مرجع الأدلة: `RAMSES_V81E_G2P_CASE_CLEARANCE_QA_AR.md`.

---

# بوابة الإصدار الحالية: V8.1E-G2O — 31 أكتوبر 2026 — NO GO

- [x] منع كشف ملفات الحالات والبحث بأسماء مرضى النقاط الأخرى لمجرد صفة «مراجع»، وربط الوصول بتفويض نقطة تحصيل نشط.
- [x] تقييد اعتماد ورد إشعار دائن أو رد مريض والتصحيح المالي وملفات الاستدراك الورقية بالنقطة المفوضة، حتى عند الدخول بمعرّف مباشر.
- [x] حماية إيصال التحصيل بالمعرّف، وحجب معرّفات حسابات المقاصة في الإيصالات غير المخصصة للمالك.
- [x] حصر ملخص المستشفى المالي الشامل للمالك، وعدم كشف أرقام كل النقاط لمراجع بتفويض جزئي.
- [x] نموذج واضح للمالك لتفويض الكاشير أو المراجع وسحب التفويض؛ حالة فارغة آمنة بعد السحب، واختبارات على 1440 و375 و320.
- [x] 73 اختبار Python/Chromium معزول: **69 PASS، 3 SKIPPED، 1 BLOCKED** لغياب V8.0. لم تتغير بيانات مستشفى حقيقية.
- [ ] RBAC لكل endpoints الأقسام والخزن والتقارير والموظفين والمرضى؛ سيناريوهات تجميع/إلغاء التفويض عبر كل الوحدات.
- [ ] الإقامة والداخلي والحضانة والعمليات والمخازن والموردين وأتعاب الأطباء وPOS العابر للشهور.
- [ ] اختبار ترحيل V8.0 الأصلي والنسخ التاريخية الأقدم، وخادم متعدد الأجهزة، استعادة خارج الجهاز، اعتماد محاسب المستشفى والإدارة.

**لم يُنشر الإصدار للاستخدام الحقيقي، ولا يجوز اعتباره آمنًا للبيانات السريرية أو النقدية الفعلية بسبب الاختبارات المحلية وحدها.**

**التفاصيل:** `RAMSES_V81E_G2O_SECURITY_QA_AR.md`.

---

# بوابة الإصدار الحالية: V8.1E-G2N — 31 أكتوبر 2026 — NO GO

- [x] منع دور المراجع العام من استيراد أو قراءة كشوف بنك من دون تفويض مالك على الحساب، ورفض قراءة ملف المصدر والتصدير والمطابقة والاعتماد غير المصرح بها.
- [x] منع الوصول المباشر بحساب بنك آخر، وسريان إلغاء المنحة فورًا، وإعادة فحصها داخل معاملة استيراد CSV.
- [x] فصل صلاحية إعداد كشوف البنك `can_submit` عن اعتمادها `can_approve`، وعدم السماح للمستورد بأن يعتمد كشفه.
- [x] اشتراط نطاق البنك ومحفظة POS معًا لإظهار بيانات تسويات بطاقات المرضى؛ واجهة صريحة للدور الفعلي.
- [x] اختبار Python شامل: 67 PASS و3 SKIPPED و1 BLOCKED من أصل 71، مع اختبار Chromium offline منفصل.
- [ ] كل الأدوار والأقسام والخزن والحسابات والمرضى تحتاج RBAC شاملاً لكل شاشة وعملية.
- [ ] ملف V8.0 الحقيقي ومصادر الإصدارات التاريخية الأخرى لتأكيد اختبارات الترقية.
- [ ] حسابات الداخلي والعمليات والحضانات والمخازن والموردين وأتعاب الأطباء، ومطابقة POS العابرة للشهور.
- [ ] اختبارات اختراق، اتصال Chromium بالخادم الحقيقي، تجارب فريق الاستقبال والمالية، macOS حقيقي، النسخ خارج الجهاز والاستعادة، اعتماد محاسب المستشفى والمالك.

**لم يُنشر أي شيء إلى نظام مالي حقيقي.** التفاصيل في `RAMSES_V81E_G2N_SECURITY_QA_AR.md`.

---

# Current release gate: G2M (31 October 2026) — NO GO

- [x] AES-256-GCM encrypted local SQLite backup, authenticated offline verification and safe no-overwrite restore on synthetic data.
- [x] Read-only GL/patient/treasury preflight catches balanced yet unsupported fund postings.
- [x] Mac launcher and unapproved UI label corrected; 12/12 selected regression tests passed.
- [ ] Real independently controlled off-device storage, real restore drills, custodian key recovery, IT/security signoff.
- [ ] Original V8.0 migration ZIP bytes accessible to the test runner; migration test remains blocked.
- [ ] Inpatient, ICU/NICU, operating room, suppliers, stock, physician accruals, comprehensive RBAC, real cash/bank acceptance.

**This package remains DEVELOPMENT / TEST ONLY: not approved for actual hospital money or patient records.**

---

# Ramses V8.1E-G2L — افتتاحيات موثقة ومستقلة / 31 أكتوبر 2026

**أحدث مرجع تنفيذ:** `RAMSES_V81E_G2L_AUDIT_QA_AR.md`.

- تنفيذ طلب إثبات رصيد افتتاحي لخزنة/بنك/محفظة قبل أول حركة، مع تفويض مستقل وتوثيق مرجع وبيان الإثبات.
- اعتماد مراجع آخر مفوض وترحيل قيد مدين/دائن مرتبط بمستند في معاملة واحدة، وعدم تسجيل نقدية أو إيراد مزدوج.
- منع الإقفال عند وجود افتتاح موجب غير معتمد أو قيد افتتاحي مختل؛ حماية المحضر المعتمد/المرفوض من أي تعديل لاحق.
- واجهة خزن عربية متجاوبة ومراجعة اختبارية على 320/375/1440 بكسل.
- 66 من 67 اختبارًا اجتازت بيئة التطوير. اختبار V8.0 متوقف على توفر ZIP الأصلي (التشغيل قابل للنقل عبر `RAMSES_V80_ARCHIVE`).
- **TEST ONLY؛ لا استخدام فعلي للأموال أو بيانات المرضى قبل استكمال بوابة التشغيل.**

---

## G2K POS clearing and bank signoff gate / 31 October 2026

- [x] Two-party POS settlement, gross/fee/net posting as one atomic transaction; avoid duplicated patient receipts.
- [x] Unique active receipts, additive migration and signed bank statement independently required.
- [x] Regression and browser-fixture tests: 62/63 scripts succeed. Old V8.0 migration archive absent.
- [ ] Accountant approval of opening balances, cross-period acquiring statements, terminal-level reconciliation and chargeback flows.
- [ ] Real Mac, production network, encrypted off-device backup and restore and hospital acceptance testing.
- [ ] NO GO: production financial or patient data forbidden.

---

## بوابة V8.1E-G2J (31 أكتوبر 2026)

- [x] مطابقة حركة الخزن والمحافظ والبنوك من سند معتمد إلى قيد الأستاذ، مع منع الإقفال للفروق.
- [x] التحقق من جرد الورديات المعتمد وكشف البنك مع تطابق حركة الفترة.
- [x] منع تعديل وحذف حركات الخزن وسجلات البنك المعتمدة عبر SQLite.
- [x] تقرير محاسبي عربي وتصدير CSV. اختبارات المشروع: **59 من 60 ناجح**؛ النسخة V8.0 التاريخية الأصلية مطلوبة لاختبار الترحيل المتبقي.
- [ ] **العمل الحقيقي ممنوع:** الأرصدة الافتتاحية والجرد الفعلي، POS، ودفاتر الداخلي والمخازن والموردين والأطباء والمحاسبة المعتمدة والاستعادة الخارجية والتشغيل متعدد الموظفين غير مكتملة.

---


## حاجز V8.1E-G2I (31 أكتوبر 2026)

- [x] منع العكس اليدوي للمستندات الآلية وقيد المريض والمقدمات (G2I tests).
- [x] ضبط حسابات الرقابة 1200/2300/2310 وفحص فروقها قبل إقفال الشهر.
- [x] منع إقفال الشهر الحالي أو القادم، واختبار صلاحيات تقارير المطابقة.
- [ ] **لا تشغيل حقيقي:** لا تزال مطابقة النقدية والبنوك والموردين والمخازن، والأرصدة الافتتاحية، وفصل الاعتمادات السريرية، والاختبارات على الأجهزة الحقيقية، والاستعادة الخارجية، ومراجعة السياسات المالية مطلوبة.

# حالة الاعتماد الحالية — V8.1E-G2G: DEVELOPMENT / TEST ONLY

تم تنفيذ تخفيض قيمة فاتورة صادرة غير محصلة عبر إشعار دائن ومراجعة مستقلة، ولا تمتد الوظيفة للفواتير المحصلة أو تصحيح المريض/إيصال الدفع. لا تشغّل البرنامج على أموال المرضى أو بيانات المستشفى الحقيقية؛ الموافقات المحاسبية الشاملة، RBAC، النسخ والاستعادة، اختبارات النشر والموظفين المتزامنين لا تزال مطلوبة. راجع `RAMSES_V81E_G2G_QA_AND_REMAINING_AR.md`.

---

Owner-confirmed V8.1E acceptance additions (PLANNED; NOT YET DONE):
- [ ] Outside 3x8h remits to independent central internal/main treasury without duplicate patient income; direct internal/surgery/NICU collections and central expenses use that same physical fund without reattributing expense to an outside shift.
- [ ] Versioned draft provisional physical handover enables next shift on counted actual cash while a prior shortage/unfinished documentation remains flagged.
- [ ] Missing EGP 1+ blocks ordinary final close; separately documented staff settlement or independent owner/explicitly authorized accountant shortfall approval produces an unbalanced-exception status with proper GL account treatment and full audit.
- [ ] Upload requirements OFF by default with independent owner-editable switches; calm +2h default dashboard notes and month/week/day RTL calendar.
- [ ] All above plus zero-double-posting, old schedule preservation, idempotent approval/variance posting and historical file backups pass end-to-end tests.
Full source: `V81E_CENTRAL_TREASURY_OWNER_DECISIONS.md`.

## إضافة بوابة قبول جديدة — خطة الورديات المرنة V8.1E

**المرجع النهائي:** `RAMSES_V81E_COMPLETE_SHIFT_CASHIER_PLAN_AR.md`. القائمة القديمة أسفل هذا السطر تتعلق بتصميم P0 السابق، وبعض بنودها عن إدخال ملخص ورقي لم تعد مطابقة لقرار المالك الأحدث.

- [ ] [P1] جدول ورديات **لكل نقطة** مع 3 خارجي +1 داخلي، وتاريخ سريان ونسخ تاريخية واستثناءات معتمدة وتغطية تنبيه صحيحة.
- [ ] [P2] تكليف الموظف وربط الخزنة/الدرج/النقطة/الفترة مع منع مشاركة عهدة من دون إثبات.
- [ ] [P3] اعتماد إقفال إلكتروني بمستندات إثبات مشروطة وسياسة انتقال إلى الرقمي الكامل.
- [ ] [P4] استدراك فواتير ومصروفات إلكترونية للوردية القديمة بوقت إدخال حقيقي وعدم إنشاء توقيعات تاريخية مصطنعة.
- [ ] [P5] مطابقة الأموال المسجلة سابقًا/غير المسجلة مع القيود والظروف والمقدمات دون زيادة قبض أو إيراد مرتين.
- [ ] [P6] يومية كل نقطة ويومية المستشفى بنسب اكتمال صحيحة ومؤشرات الجزئي/المجهول/قيد المراجعة.
- [ ] [P7] استرجاع نسخة مستقلة، صلاحيات RBAC مفعلة، اختبارات تزامن، فواتير، جرد، تنبيهات، تواريخ عبر منتصف الليل والتوقيت الصيفي، ومراجعة محاسب مختص.

**الحالة الآن:** P0 فقط منفذ تجريبيًا؛ التخطيط الجديد لا يعني تحقق بنود القبول.

---

## V8.1E mandatory future acceptance gate (shift-first owner decision)

- [x] Read-only point/day electronic coverage and provisional daily summaries tested on isolated fake data; zero financial writes.
- [ ] Historical expected shift calendar and owner-approved non-operation exceptions prevent false missing alerts; monitoring start date and real activation known.
- [ ] Late paper-sheet and cash-envelope records with actual receiver, custodian and entry operator, including hybrid summary/detail modes and mixed payment methods.
- [ ] Prior-posted cash matching, idempotent adjustments and no silent mutation to approved shifts or closed months.
- [ ] All expected station shifts included in financial-day certification; drill-down invoices, advances, expenses, envelopes, custody chain and exception approvals.
- [ ] Scoped RBAC V8.1D and independent two-person financial approvals; tested backup, real concurrent cashiers, full Chromium HTTP/browser tests and restoration.

**No real financial operation until all boxes and M7 pass.** Details in `SHIFT_FIRST_DAILY_MONITORING_PLAN_V81E.md`.

---

## بوابة صلاحيات M3.5 (قرار المالك — غير منفذة حتى الآن)

- [ ] اعتماد قوالب أدوار متعددة وصلاحيات الصفحات/الأوامر ونطاق البيانات مع التحقق من الخادم.
- [ ] حق إدارة صلاحيات الآخرين **OFF افتراضيًا لكل غير المالك**، ومفتاح تفويض فردي لا ينقله دور آخر؛ المالك وحده يفعل ويعطل، بعد تحذير وتأكيد وإعادة تحقق.
- [ ] المفوّض لا يغير حسابه أو المالك، ولا يوسّع صلاحياته أو نطاقه ولا يمنح تفويضًا لغيره؛ أي تغيير يترك أثرًا وتنبيهًا للمالك.
- [ ] تعدد أدوار الكاشير/المراجع لا يلغى منع اعتماد المستخدم لمعاملاته أو جرد ورديته.
- [ ] منع تصعيد صلاحية عبر API مباشرة، وحالات جلسات قديمة وتزامن، واختبارات ترقية وحفظ بيانات V8.1C.

المواصفات التفصيلية في `ACCESS_CONTROL_RBAC_PLAN_AR.md`. **هذه متطلبات مستقبلية وليست وظائف منفذة حاليًا.**

---

# V8.1B — بوابة القبول الحالية (لا تُتجاهل)

يمكن إصدار فواتير مرقمة تجريبيًا وتسجيل تحصيلات مختلطة ومقدمات ذات قيود مزدوجة مع حماية من التكرار. **هذا لا يعني الجاهزية الإنتاجية**. لا يجوز التشغيل الحقيقي قبل وجود آلية رد/إشعار دائن وموافقة منفصلة، وإقفال عهدة بنقطتي تحصيل بتوقيعين، وتسوية POS والبنك، واعتماد سياسات الإيراد والضرائب والعقود والنسخ والاسترجاع خارج الجهاز واختبار العمل المتزامن. الخطة الملزمة `RAMSES_MASTER_PLAN_AR.md`، والتقدم `V8_1B_PROGRESS_AR.md`.

---

# تنبيه إصدار V8.1A: نقطة الكاشير الداخلي والخارجي تستخدمان مسودات تجريبية فقط، بدون خزنة فعلية أو قبض/إيراد، ولا يسمح إقفال شهر به ملفات الحالات غير المرحلة. الخطة الملزمة `RAMSES_MASTER_PLAN_AR.md`.

# تحديث بوابة القبول — V8.0 (30 أكتوبر 2026)

تمت إضافة **نواة دفتر الأستاذ مزدوج القيد** مع ترحيل السندات الجديدة، واستحقاق المرتبات، والقيود اليدوية المراجعة، وميزان مراجعة **جزئي وغير معتمد**. راجع `V8_0_PROGRESS_AR.md` و`ACCOUNTING_V8_0_GUIDE_AR.md` و`RAMSES_DECISION_SYSTEM_ROADMAP_AR.md`.

**قرار ملزم:** يمنع اعتماد ربحية أو قوائم مالية للمنظومة الآن؛ يلزم اعتماد الافتتاحية، ودورة فواتير المرضى والذمم، والموردين والمخزون والتكلفة وأتعاب الأطباء والتسويات والإقفال، مع اختبارات أمن واستعادة. جميع البنود أدناه توثيق تراكمي تاريخي من V7.6 ولا يُقرأ على أنه القائمة النهائية الحصرية في V8.0.

---

# بوابة قبول نظام حسابات مستشفى رمسيس — V7.6

**حالة حاكمة:** لا شراء خادم، لا نشر، لا حسابات مستشفى حقيقية، ولا مزامنة مع الشيت الأصلي قبل اجتياز القبول. لم تُعتمد النسخة إنتاجيًا. راجع `V7_6_PROGRESS_AR.md` و`BANK_RECONCILIATION_V7_6_AR.md` للتطوير الحالي وحدوده.


**القرار:** لا شراء VPS أو Mini PC، ولا GitHub Actions، ولا نشر على الإنترنت أثناء التطوير. أي اتصال بالمستشفى أو Google Sheets الحقيقي مؤجل حتى نجاح الاختبارات واستكمال الجاهزية.

**النطاق المستهدف الآن:** نظام حسابات أولي داخلي لإدارة المقبوضات والمدفوعات والتحويلات والخزن والسلف والمرتبات والاعتمادات والتقارير. نظام إدارة مرضى/مخزون متكامل وقائمة أرباح وخسائر وفق أساس الاستحقاق ليست وظائف مكتملة في هذا الإصدار.

## الحالة بعد تطوير V7.6

| المجال | المتحقق حاليًا | ما يمنع اعتماد تشغيل حقيقي |
|---|---|---|
| سندات الإيراد والصرف والتحويل | يعمل محليًا؛ فصل المُدخل عن المُعتمِد؛ حفظ ذري ورفض السحب من رصيد غير كافٍ | اختبار سيناريوهات موظفين متعددة، ومستندات الإثبات، وتنظيم مراجع الفواتير |
| التسوية العكسية | قيد عكسي يحفظ الأصل؛ يمنع عكس قيد عهدة فرق جرد بطريقة عادية؛ شمل الاختبار مجموع حركة الموظف حتى لو أنشأ المالك العكس | اختبار عكس المستندات عبر شهور مختلفة والتقارير بعد إقفال الفترات |
| صلاحيات المستخدمين | تسجيل دخول وأدوار، إنشاء حساب، تعطيل/تفعيل حساب، تغيير كلمة المرور مع تأكيد كلمة مرور المدير، وإلغاء الجلسات | اختبار جميع الأدوار عمليًا مع فريق العمل، والتحقق من سياسات الاطلاع على الرواتب |
| رصيد الخزنة والوردية | **تم محليًا:** فتح وردية، جرد فعلي أعمى، فرق جرد، مراجعة مستقلة، كشف تفصيلي للحركة، إعادة عد، منع ترحيل أثناء المراجعة ومنع إقفال شهر به وردية معلقة | توقيع وتسليم العهدة بين طرفين، محضر تسوية فروق معتمد، تجربة جرد ميدانية وتصدير محضر رسمي |
| المرتبات | إعداد راتب، كشف استحقاق، سلفة وتسويتها وصرف راتب، تصحيح موثق قبل الصرف، وتصدير CSV محدود الصلاحية | **أُنجز في V7.5:** أجر شهري وبالساعة وسجل ساعات؛ بنود يدويّة للإضافي/الخصم/الإجازة؛ مراجعة منفصلة للبنود؛ اعتماد ثانٍ إلزامي للكشف قبل الصرف؛ منع الإقفال مع كشوف معلقة. **المتبقي:** سياسة قانونية/إدارية دقيقة للإضافي والغياب والتأمينات والضرائب، وبصمة حضور وتطبيقها بعد اعتمادها |
| الإقفال الشهري | حظر السندات الجديدة في الشهر المغلق، ورفض إقفال شهر به سندات أو ورديات أو بنود/كشوف مرتبات معلقة؛ **V7.6** يمنع الإقفال مع حركات بنكية بلا كشف مطابق معتمد | إغلاق معايير المديونيات وأرصدة السلف والرواتب وتوقيع الإدارة |
| **مطابقة كشف البنك V7.6** | استيراد CSV تجريبي، ربط يدوي 1:1، منع التكرار، اعتماد مستقل عن الاستيراد، قفل الشهر البنكي، حفظ المصدر وسجل المراجعة | **جزئية:** لا تحويلات عابرة للأشهر أو تجميع حركات أو رسوم آلية؛ يلزم اختبار كشوف واقعية بإذن لاحق وشهادة مراجعة مستقلة |
| التقارير | نقدية حسب القسم والنوع، ملخص استرشادي مع تحذير واضح | **ليست قائمة أرباح وخسائر رسمية**؛ المخزون والمستحقات والإهلاك والموردون غير مكتملة |
| بيانات يونيو 2026 | أرشيف معزول، لا يُرحل تلقائيًا للخزن | التسوية المستندية، توحيد الأقسام وتحديد الأرصدة الافتتاحية الفعلية |
| Google Sheets | مزامنة اختُبرت بمحاكاة، ونسخة اختبار خاصة منفصلة | اختبار اتصال فعلي بحساب خدمة محدود الصلاحية، ومطابقة عدّ الصفوف والأرصدة |
| الحماية والنسخ | CSRF، Cookies وقيود أدوار، اختبارات محلية للنسخ SQLite | تجارب استرداد بيانات معزولة، نسخة مشفرة خارج الجهاز، حماية Cloudflare Access أو VPN |
| واجهة الكمبيوتر والموبايل | شاشتا الورديات والمرتبات والاعتماد اختُبرتا في Chromium **دون شبكة ومع بيانات وهمية** على كمبيوتر وموبايل؛ واختبارات API ناجحة | **اختبار متصفح HTTP كامل لم يكتمل** بسبب قيود البيئة؛ الاختبار اليدوي مطلوب لباقي الشاشات |
| الاستضافة | ملفات تشغيل محلي ودليل Mini PC موجودة | تأجيل قرار VPS مقابل Mini PC والتكلفة حتى نجاح كافة البنود الحرجة |

## أولويات التطوير التالية — لا يتم اعتبارها منجزة قبل اختبارها

**P0 — محاسبي وأمني (يجب قبل التشغيل):**
1. [منجز جزئيًا V7.2] دورة الوردية البرمجية والجرد الأعمى والإقفال المزدوج وربط الحركة بالوردية. **المتبقي:** تسليم العهدة بتوقيع طرفين وتصفية العهد المعلقة رسميًا بعد التحقيق؛ لا تُقفل وردية غير مطابقة دون محضر واعتماد مستقل.
2. [أُنجز جزئيًا V7.3] مرفقات السندات مشروطة بصلاحيات وحجم ونوع وتحفظ في SQLite؛ **المتبقي فحص AV/CDR وسياسة الاحتفاظ بالملفات واشتراط المستندات بحسب التصنيف المالي**.
3. [أُنجز جزئيًا V7.6] مطابقة كشف البنك اليدوية داخل الشهر؛ **المتبقي** الحركات العابرة للشهور وتجميع الحركات وتسوية الرسوم، بجانب المطابقة الشاملة للخزن والتحويلات والسلف والمرتبات.
4. قرار مالك المستشفى حول صلاحيات الاطلاع على رواتب العاملين وأسماء المرضى داخل القيود.
5. اختبارات اختراق وظيفية: محاولات صلاحيات غير مصرّح بها، إنشاء سند مكرر، طلبات متزامنة، إلغاء حساب موظف أثناء الجلسة، وإدخال بيانات غير صالحة.
6. خطة استرداد: نسخ آمن بعيد عن الخادم مع استعادة ناجحة ومؤرخة على قاعدة اختبار مستقلة.

**P1 — تشغيلي قبل التسليم للموظفين:**
1. اختبار يدوي من محاسب ومراجع على موبايل وكمبيوتر: إنشاء/اعتماد/رفض/عكس/تصدير/بحث/ترحيل.
2. تثبيت معايير تسمية الأقسام وحسابات النقد/المحافظ والبنوك، وجمع الأرصدة الافتتاحية المعتمدة.
3. تجربة اتصال Google Sheets على حساب الخدمة المخصص لشيت التجارب فقط، ثم مقارنة أعداد السندات ومجموع القروش بعد عملية موافقة وعكس.
4. تعديل تجربة الاستخدام حسب المشكلات المرصودة، وتوحيد النسخ والتواريخ بالعربية وتوقيت القاهرة.

**P2 — تطور لاحق حسب نطاق المستشفى:** إدارة الموردين/المديونيات، المخزون والمستلزمات والأصول، الإيراد المستحق، تقارير الربحية المعتمدة، وربط الفواتير ونظام استقبال المرضى.

## شروط السماح بشراء الاستضافة أو الجهاز

- لا توجد أعطال حرجة مفتوحة أو اختلافات مالية في سيناريوهات القبول.
- كل صلاحية مجرّبة بحساب منفصل، والحساب المعطل لا يعود إليه الوصول بعد قطع جلسته.
- خزن وورديات مُطابقة فعليًا من صاحب العهدة؛ رواتب وأرصدة افتتاحية مُعتمدة من الإدارة.
- نجاح اختبار قطع الاتصال وإعادة المحاولة دون سند مكرر، ونسخ احتياطي مشفر واختبار استرداد موثق.
- انتهاء الاختبار اليدوي على الموبايل والكمبيوتر، وتوثيق قبول الإدارة للحزمة المختبرة.
- **بعدها فقط** مقارنة VPS/Mini PC وتكاليف التخزين/النسخ وقرار النشر الآمن، ثم تجهيز بيئة فعلية نظيفة دون بيانات الاختبار.

## أدلة اختبارات هذه النسخة

```bash
python tests/test_system.py
python tests/test_user_lifecycle.py
python tests/test_deployment.py
python tests/test_google_sync.py
python tests/test_local_server.py
python tests/test_shifts.py
python tests/test_shift_migration.py
python tests/test_payroll_review_workflow.py
python tests/test_bank_reconciliation.py
python tests/test_bank_migration.py
python tests/browser_bank_offline.py
python tests/test_mixed_payroll_migration.py
python tests/browser_payroll_review_offline.py
python tests/browser_shifts_render_offline.py
node --check static/app.js
```

نجحت **16 مجموعة اختبار للخادم** وأربعة اختبارات Chromium تمثيلية منفصلة دون بيانات مستشفى حقيقية، منها `test_bank_reconciliation.py` و`test_bank_migration.py` و`browser_bank_offline.py`. اختبارات المتصفح تُعرض بدون اتصالات HTTP حقيقية. اختبار المتصفح الآلي الاختياري `tests/browser_smoke_optional.py` لم ينجح في هذه البيئة بسبب `ERR_BLOCKED_BY_ADMINISTRATOR` عند فتح `127.0.0.1`؛ لا يُعد عيبًا مؤكدًا في التطبيق ولا دليلًا على سلامة الواجهة؛ يجب إعادته ببيئة تسمح بذلك.

**مهم:** لا توجد موافقة على شراء أو نشر. لا تُنشئ خدمات مدفوعة أو تشارك أصول أو شيت إدارة أو كلمات مرور مع بيئات تجريبية.

## ما يجب ألا يُفهم من هذه المرحلة

- لم تُراجع بيانات يونيو الفعلية مستنديًا ولم تُعتمد الأرصدة الافتتاحية، ولا توجد بيانات مرضى/رواتب حقيقية في حزمة التسليم.
- مسار فروق الجرد أصبح يدعم قيد عهدة مؤقتة وموافقة محضر، لكن **تصفية العهدة المحاسبية النهائية** لم تكتمل بعد، وبالتالي وحدة الورديات **ليست جاهزة للتشغيل المالي الحقيقي منفردة**.
- لا شراء استضافة، لا نشر، لا تعيين صلاحيات عامة لموظفين، ولا تفعيل Google Sheets الإنتاجي.

**تذكير V7.6:** الموافقة على كشف البنك لا تثبت أصالة مصدر البنك. لا تستخدم نسخة التطوير لمطابقة متحصلات المستشفى الفعلية، ولا تعتبر مطابقة نهاية الشهر مكتملة عند وجود تحويلات تحت التحصيل أو حركات عابرة للأشهر.


### V8.1C cashier shift release controls - still pending
- Confirm owner-approved local working hours and set strict shift-clock mode ON for production.
- Test refunds against actual payment-provider reversal policy and approved payer identity.
- Test independent handovers with cash denominations and uninterrupted desk turnover.
- Validate full credit-note/legal invoice requirements with licensed local accountant.
- Prove off-device encrypted backup and restore and real Google Sheets test sync.
- Run multi-user live integration/security tests before financial records enter the system.

## ملحق بوابة التشغيل — متطلبات V8.1D/V8.1E بعد تدقيق 30 أكتوبر 2026

- لا تشغيل حيًا قبل تفعيل الجدول المرن حسب النقطة (3 خارجي و1 داخلي كبداية) والتحقق من تاريخ السريان وحفظ السجلات التاريخية بما فيها النقاط المعطلة والفترات غير المسجلة.
- لا قبول محاسبي لمبلغ متأخر قبل التمييز بين نقدية محفوظة ماديًا ونقدية مرحّلة، ومنع تكرار الإيصال أو الفاتورة أو تحويل النقدية كإيراد.
- تسليم العهدة والجرد لا يساويان اعتماد اليومية المحاسبي؛ ممنوع الاعتماد الذاتي حتى مع تعدد الأدوار.
- كل الفواتير والتحصيلات والمصروفات إلكترونية؛ الصور دليل أو طوارئ؛ لا دفتر ورقي موازٍ يُرحّل إجمالياته.
- يجب اختبار التغييرات بين 1/2/3 ورديات لنفس النقطة، تبادل الموظفين والخزن، الإقفال والعمليات المتأخرة والشهر المقفول، وسيناريو انقطاع الاتصال، ونسخ الملفات واسترجاعها.
- المواقيت وخريطة الخزن وسياسة إلزام الصور وحدود المراجعة والإقفال يحددها المالك والمحاسب قبل قبول التشغيل الحقيقي.

### إضافة G2F إلى بوابة الاعتماد — 31 أكتوبر 2026

- [x] اختبار رد زيادة مُثبتة بحساب 2190 مع مستندَي مطالبة واستلام مستقلين ومراجع مُفوّض، وصرف مرة واحدة فقط، ورفض القيد اليدوي على حساب الزيادة.
- [ ] اعتماد سياسة التعامل مع زيادات غير معروفة صاحب الحق والردود التاريخية والتصحيحات المعتمدة من محاسب مستقل وإدارة المستشفى قبل التشغيل الحقيقي.
- [ ] الاختبار المتصل على خادم/جهاز Mac فعلي، المزامنة الحقيقية، واسترجاع Backup مشفر خارج الجهاز، وقرارات نشر إنتاجية.
