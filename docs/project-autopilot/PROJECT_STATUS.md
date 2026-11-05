# S14 — أحدث مرحلة موثقة /5 نوفمبر2026 / TEST ONLY

من S13 `30fb06b` على `development/s14-pricing-and-payment-options`: قوائم وأسعار حسب المكان، تكلفة استرشادية، باقات بخصم موزع وسعر محفوظ إلى الفاتورة وGL، أتعاب ثابتة/نسب من المحصل ومراجعة مستقلة لكل مرة وشخص قبل إثبات المستحق، وخمس وسائل قبض وعدة إيصالات ومقدم. واجهات المالك والكاشير والمراجع فعلية مع Cairo/RTL وبطاقات هاتف.

**التحقق:**159 =154 PASS +5 SKIP، بلا FAIL/TIMEOUT/BLOCKED؛ CI82/82 مجموعة فرعية. V8.0 الأصلي PASS، ومخططS13 الأصلي رُقي مرتين مع استعادة مشفرة. Chrome375/1440 عبرHTTPS حقيقي: باقة500→450، تكلفة تقديرية145، قبض400 وباقي50؛ النقدية150 والإلكتروني250؛ قبول مستحق100 ورفض100 لمرة أخرى. إلغاء الباقة قبل التنفيذ وPDF مرئيان. فُتحت وردية تدريب5 نوفمبر برصيد صفر بعد إقفال المثال مستقلًا.

[تقرير المرحلة](S14_RELEASE_REPORT_AR.md) — [دليل S14](S14_USER_GUIDE_AR.md) — [التبديل بين Chat وWork](../../00_CONTINUE_IN_CHAT_OR_WORK_AR.md). أحدث رابط وبيانات دخول في `private/S14_ACCESS.txt` خارجGit؛ النفق مؤقت، وجُدد بعد انتهاءDNS القديم.

**PRODUCTION NO-GO:** دورة التأمين، الآجل التعاقدي، دفتر المريض عبر الحالات، صرف مستحقات الأشخاص، ربط أهلية قوائم الأسعار، FIN-01 وبقية الدورات والاعتمادات والاستعادة الميدانية والمعدات وUAT ما زالت مطلوبة. كل أمثلة المعاينة مولدة، لا مرضى أو نقدية حقيقية. الأقسام التالية سجل تاريخي.

---

# S13 — أحدث مرحلة موثقة / 4 نوفمبر2026 / TEST ONLY

استكمال من S12 `a4485e0` على `development/s13-cashier-printing`: حساب كاشير خارجي تجريبي، وفاتورة وإيصال وملخص وردية قابلون للطباعة بصلاحيات القراءة الأصلية، RTL/Cairo محلي، A4/80مم. نجحت رحلة الكاشير عبر HTTPS والمتصفح مع توثيق الخدمة واستلام واعتماد مستقلين بحسابات منفصلة. توجد حالتان جاهزتان للتدريب100 جنيه لكل حالة ووردية تالية برصيد بداية صفر.

**الدليل الحالي:**154 =149 PASS +5 SKIP، بلا FAIL/TIMEOUT/BLOCKED؛ CI78/78 PASS (جزء من المجموعة). ترحيل V8.0 الأصلي PASS. Chrome375/1440 وروابط الطباعة وPDF مرئية؛ لم تُختبر طابعة المستشفى. الأسرار والقاعدة خارجGit والحزمة؛ دليل الدخول محليًا `private/S13_CASHIER_ACCESS.txt`.

[تقرير المرحلة](S13_RELEASE_REPORT_AR.md) — [دليل الكاشير](S13_CASHIER_GUIDE_AR.md) — [التبديل بين Chat وWork](../../00_CONTINUE_IN_CHAT_OR_WORK_AR.md).

**PRODUCTION NO-GO:** FIN-01 بانتظار اعتماد رئيس الحسابات؛ ثم تكامل الاستحقاق والإقفال،2200 والمخازن والأطباء والتأمين والضرائب والأصول، الاستعادة المستقلة والمعدات وUAT واعتمادات المستشفى. لا يمثل اكتمال تجربة الكاشير اكتمال منظومة المستشفى. الأقسام التالية سجل تاريخي.

---

# S12 — أحدث حالة موثقة / 4 نوفمبر 2026 / TEST ONLY

من S11 `0acb2db` على الفرع `stabilization/s12-request-limits-preview`: أُصلح حجم الطلب قبل التحليل، وفتح قاعدة التشغيل دون إنشاء بديل عند فقد التخزين، وتهيئة الديمو مع Secure cookies. ثُبتت نسخ محلل الطلبات المختبرة. حُل تعطل المعاينة بطريقة حماية مستقلة بكلمة مرور أمام التطبيق، واختُبر الدخول عبر HTTPS حقيقي في Chrome.

**الدليل الحالي:** المجموعة 153 =148 PASS و 5 SKIP ، دون FAIL/TIMEOUT/BLOCKED ؛ CI77/77 ؛ اختبارا S12 عبر 21 طلب TCP ، واليوم المالي الموحد عبر 161 طلب HTTP ؛ Chrome375/1440 عبر الرابط الخارجي مع دخول وتحديث واستمرار الجلسة و Secure/HttpOnly و RTL/Cairo. ترحيل V8.0 الأصلي PASS ضمن المجموعة. فحص Python: لا ثغرات معروفة في الاعتماديات المثبتة وقت الفحص.

**المتبقي:** استحقاق الإقامة ونهاية الشهر، وسياسة 2200 وأرصدة الافتتاح، والمخازن المتعددة والجرد، ودورة الأطباء والتأمين والضرائب والأصول والإقفال السنوي، واعتماد صلاحيات التشغيل والتعافي والمعدات و UAT. لم تُفعّل سياسة مالية غير معتمدة. الرابط تجريبي مؤقت ببيانات مصطنعة؛ لا يعد نشرًا للمستشفى.

[تقرير المرحلة](S12_RELEASE_REPORT_AR.md) — [دليل S12](../../README_S12_AR.md). **PRODUCTION NO-GO.** الأقسام التالية سجلات إصدارات سابقة، وليست نتائج الجولة الحالية.

---

# S11 — الحالة الحالية، 4 نوفمبر 2026 / TEST ONLY

استُعيد المصدر من S10 `49167d9` على `stabilization/s11-operational-review`. أُصلح حفظ مستخدم/موظف/خزنة دون audit عند الفشل، وإقفال حالة مع صرف مخزون معلق، وغموض استثناءات اليومية. عولج تشغيل المتصفحات عبر المنصات، وحُدثت cryptography إلى50.0.2 بعد فحص أمني وتوافق النسخ.

**الدليل الحالي:** الاختبارات الشاملة150 =145 PASS +5 SKIP، صفر FAIL/TIMEOUT/BLOCKED، exit0؛ CI74/74، exit0. ترقية مخطط V8.0 من الأرشيف الأصلي المقدم PASS على بيانات وهمية، واستعادة نسخة46.0.7 بواسطة50.0.2 متطابقة منطقيًا. فحص الاعتماديات المثبتة: لا ثغرات معروفة وقت الفحص.

**ما زال مفتوحًا:** عيب فوترة ليلة آخر الشهر (مقترح جاهز لاعتماد رئيس الحسابات)، حد حجم الطلب قبل parsing، فتح runtimeDB عند فقد الملف، مصدر العميل خلفproxy، دورات الأطباء والتأمين والضرائب والأصول والإقفال السنوي والمخازن المتعددة، والقبول والتعافي الفعلي وأرصدة الافتتاح الموقعة.

[المراجعة الشاملة](S11_COMPREHENSIVE_REVIEW_AR.md) — [مقترح الإقامة](MONTH_END_STAY_POLICY_PROPOSAL_AR.md) — [دليل S11](../../README_S11_AR.md).

**PRODUCTION NO-GO.** لا نشر أو وصول لبيانات تشغيل. كل الإشارات التالية إلى غياب أرشيفV8.0 أو أعدادS10 محفوظة كسجل تاريخي؛ النتيجة الحالية أعلاه هي الأحدث. ترحيل مخطط أصلي لا يعوض ترحيل قاعدة المستشفى.

---

# S10 — cashier daily completion on approved non-working weekdays (TEST ONLY)

New synthetic acceptance proves one active station can be fully closed while a second station is `not_required`; only required points participate in the daily aggregate, with unknown/missing still provisional. The accounting-certification flag is untouched. The UI labels off-day status in Arabic; existing Chromium fixture no longer assumes October 2026. No hospital deployment; signoffs and V8.0/off-device recovery remain blocked.

**Verified on synthetic local source:** CI 71/71 PASS (exit 0); full source suite 147 = 141 PASS / 5 SKIP / 1 BLOCKED_NO_V80 (exit 0); Chromium desktop/mobile PASS; S4 integrated local TCP 161 requests PASS and S9 33 requests PASS. V8.0 source remains missing; no hospital UAT or production authorization.

---

# Current S9 - opening shift choices, 2026-11-02 - TEST ONLY

Source on isolated `stabilization/s9-date-aware-shift-creation`, base S8 `ac090681`. The general cashier screen and patient-billing opening form no longer use the latest stored schedule as if it applied to every date. Authenticated, non-mutating `GET /api/shifts/open-options` returns station- and date-appropriate choices, masked by weekday, point lifecycle and individual clerk grants, and reports preview-only for future dates. Two JS forms use an asynchronous shared picker with disabled submission and stale-response suppression. POST still does final checks. Direct TestClient, real local Uvicorn HTTP (33 requests), Chromium 1280/375 and S2/S8 smoke have passed. No production/accounting data touched. Final source CI **70/70 PASS**; source-wide regression **146 = 140 PASS / 5 SKIP / 1 BLOCKED_NO_V80**, 0 FAIL/TIMEOUT; S9 HTTP 33 and S4 HTTP 161 PASS. Evidence in `QA_S9_*` and `docs/project-autopilot/TEST_REPORT.md`. Physical hospital acceptance is NOT established.

**Verified S9 gates:** CI 70/70 PASS; full source QA 146 = 140 PASS / 5 SKIP / 1 BLOCKED_NO_V80 with 0 FAIL/TIMEOUT; genuine localhost S9 HTTP 33/33, S4 integrated HTTP 161, Chromium 1280/375. All run with synthetic disposable data; full V8.0 migration and hospital UAT remain blocked.

PRODUCTION NO-GO: V8.0, off-device recovery, physical HTTPS/LAN/printer UAT, finance/medical/IT approval and accountant-approved supplier 2200 policy outstanding.

---

# Current — S8 historical cashier shift identity (2026-11-02; TEST ONLY)

**Implemented:** effective-dated server `shift_name` on shift list, per-shift daily report and consolidated hospital cashier day; RTL desktop/mobile consumes historical label. Source API RED when field absent and GREEN after fix. Browser RED on latest-plan mislabel and GREEN on historical label; recovered the existing frozen-month UI test. Real local Uvicorn HTTP S8 test checks owner/viewer auth and zero ledger writes. Previous money controls S2/S4 and scope G2W retain separate verified test evidence. Final suite and artifact evidence are tracked in the S8 release QA report. **PRODUCTION NO-GO**: missing genuine V8.0, independent physical recovery, HTTPS hospital workstation tests, signed finance/medical/IT approval. No live writes or migrations.

---

# Current — S7 offline recovery rehearsals (2026-11-02; TEST ONLY)

**S7 current regression:** 68/68 source CI PASS, full QA 144 = 138 PASS / 5 SKIP / 1 BLOCKED_NO_V80, 0 FAIL; S4 HTTP synthetic 161 requests PASS. No second real device demonstrated.

From S6 `8feca982`, prepared operator-executable offline recovery on a *new path* using independently recorded encrypted SHA256 plus S6 AES and ledger/evidence integrity gates. Separate Python FastAPI smoke checks HTTP 200 health and 401 unauthenticated API against a disposable copied DB; the restored archive stays byte-for-byte intact. Output report excludes patient/financial records. S7 source regression covers wrong SHA, password, tampered ciphertext and existing/symlink target. This does **NOT** assert a second machine was used. No migrations, live financial writes, deployment, external data transfer, or bank actions. CI/full source evidence must be read from release QA artifact. **PRODUCTION NO-GO** pending genuine V8.0, physical external restore and IT/finance/medical signoffs.

---

# Current: Ramses Accounts — S5 HTTP / SQLite concurrency (2026-11-02, TEST ONLY)

Branch `stabilization/s5-contention`, S4 baseline `60bddc1`. **Locally implemented and tested:** fix FastAPI cross-thread SQLite connection failure (`check_same_thread=False` with request-scoped connection), remove earlier 10-second SQLite busy timeout override and inherit 30-second connect timeout. Real Uvicorn baseline RED: 96 HTTP requests with 65 HTTP 500 and 17 connection errors, SQLite `ProgrammingError`; second RED at 384/48: one `database is locked`. Final GREEN at 384/48: 384 HTTP 200, 12 unique active point grants, 384 audit events, 403 on unauthorized assignment, integrity/FK clean. S4 integrated in-process and 161 real HTTP pass; eight targeted financial/security/backup regressions pass. **Full S5 CI 66 test suite not completed (time limit, only five observed pass).** No product UI/GL/schema/finance policy change. No deployment or live patient records. **NO-GO PRODUCTION** pending true V8.0 archival migration, off-device encrypted recovery, independent hospital finance/medical/IT signoffs, real HTTPS browser/LAN/printer UAT and performance/load acceptance.

---

# Current: Ramses Accounts - Stabilization S4 (2026-11-02, TEST ONLY)

Branch `stabilization/s4-integrated-day`; baseline S3 `4e425e4`. Verified one synthetic shared-DB financial day across patient/cashier/historical envelope/supplier/bank plus protected month-close preflight; full QA **135 PASS / 5 SKIP / 1 BLOCKED_NO_V80**, CI **66/66 PASS**. Genuine separate Uvicorn HTTP exercised 161 requests. Production NO-GO: no true V8.0 migration, off-device restore, real browser HTTPS, hospital UAT or independent sign-offs. Intermittent setup HTTP 500 during parallel test load remains an explicit open load-risk, not a proven fixed bug. Read `README_S4.md`, S4 section of `TEST_REPORT.md` and release QA summary before using.

---

# Ramses Accounts - Stabilization S3 (TEST ONLY; 2026-11-02)

Base commit: `3e9669229b5ecc3da954416c1a541ff8642ea71c` (S2). Branch:
`stabilization/s3-http-late-entry-acceptance`. No financial production
code, SQLite schema, prices, staff permissions or hospital data were changed.

## Implemented

- An isolated `requests.Session` transport drives **unchanged legacy real API
  workflows** over a genuine separate-process Uvicorn HTTP socket and
  disposable SQLite; clients have independent cookie jars.
- 5 synthetic HTTP gates: S2 full 24h cashier day; treasury deposit retry/race;
  G2B prior-month late invoice; G2D three mixed-envelope reconciliations;
  cookies, CSRF, login and role rejection. Historical evidence upload uses
  actual multipart HTTP. All are independent scenarios, NOT a unified day UAT.
- Strengthened S2 cashier daily-report regression: independently-closed
  morning/evening/night reports, central 600/50/550 EGP ledger reconciliation,
  server-side denial of a clerk reading another shift's detailed report.
- Source tests stay in original files and shared test transport lives in
  `tests/s3_http_transport.py`; run from `scripts/qa_s3_real_http.py` so the
  older 140-script source suite does not accidentally include network tests.

## Evidence limitation and release gate

This validates local **HTTP over TCP**, not browser-to-HTTP. The existing
Chromium test was rerun and returned `net::ERR_BLOCKED_BY_ADMINISTRATOR` for
loopback navigation. No TLS/HTTPS/certificate, hospital firewall/proxy,
physical devices/printers, real cashier staff or connected hospital UAT was
verified. No V8.0 original archive or independent encrypted off-device
restore was available. No production deployment. **PRODUCTION NO-GO**.

Next unblocked work: retain a sealed synthetic workday combining shifts,
patient receipts, delayed evidence, supplier bank settlement and independent
GL/subledger preflight. The full 24h plus mixed-envelope suites above do
not yet prove that combined scenario in the same database.

---

# Ramses Accounts — Stabilization S2 (TEST_ONLY)

Date: 2026-11-02 (Africa/Cairo)
Source baseline: G3N-S1, commit `1c35cb57812b0cde6670b7d1a5e3f07c95e550be`.
Working branch: `stabilization/s2-cashier-acceptance`.
Operational status: **STAGING / NO-GO PRODUCTION**. No hospital data was used, no live DB migrations were applied, no release was deployed, and no accounting policies were changed.

## Implemented and locally verified

- 24-hour synthetic cashier operation across night (100 EGP), morning (200), evening (300), and central treasury: independent receipt approval, blind counts, independent cash handovers and accounting closure; 600 EGP transferred, 50 EGP central expense, 550 EGP final treasury; source external cash zero; balanced GL and correct revenue once.
- Cashier partial treasury deposits now accept `client_request_id` as an optional stable retry token. Duplicate keys with matching payload/user replay the **existing** voucher; mismatched payload/user rejected 409. All checks and posting use the same `BEGIN IMMEDIATE` SQLite transaction. Ordinary vouchers retain their own independent request-key namespace.
- Physical source shift + trimmed case-insensitive note is treated as one unique envelope/handover reference even when a retry uses a new token. Additional installments need distinct original references.
- The accepted real handover receiver, if the current internal treasury cashier, can complete treasury receipts directly through the existing shift screen, including after independently approved external shift closure, before a newer external shift takes custody. Server rechecks all permissions. New action uses role-informed `can_treasury_deposit` / remaining amount response.
- Fixed an existing UI defect: cashier shift schedule slots previously lacked `end`, causing literal `undefined` in the shown clock; recompute per-point effective slot end and label internal one-slot schedules to end of day.
- Confirmed 375/1440 px Chromium UI with real FastAPI TestClient/SQLite bridge (not real HTTP transport). Synthetic tests only; no production deployment.

## Not verified / release blockers

1. Original actual V8.0 archive was unavailable, so historical migration/backup and opening balances remain unaccepted.
2. No real-browser-to-HTTP/TLS, WAF, reverse proxy, trusted device or physical LAN tests. Chromium loopback is administratively blocked in this sandbox; TestClient bridge is not a substitute.
3. No independent off-device encrypted restore, hardware failure drill, financial officer approval, clinical workflow sign-off, or 24-hour real staff pilot.
4. Payment source documents and patient/doctor verification are not independently authenticated. External reference transcription and operator input can still be wrong; a changed/falsified physical reference cannot be reliably detected without signed/evidence-matched custody documents.
5. Existing API callers omitting `client_request_id` still work for backwards compatibility but cannot replay their **same** prior result by token. However identical physical `source_shift_id`+`note` is rejected even with a new token.
6. A client UI retry token survives network errors while the current page remains open, not a full browser/device restart. The physical-reference conflict blocks the same reference being booked again but requires reconciliation if a confirmation response was lost.
7. Supplier control ledger vs GL (2200) is not yet a signed period-close policy; insurance, pharmacy/drug stock, multi-store, surgeon contracts/fee splitting and approved medical discharge policies are not part of S2.

## Next 3 executable gates

- S3: independent, secured staging network smoke with actual cookies, CSRF, TLS and per-role controls at 375/1440; real device acceptance.
- S4: add late-entry/envelope scenario spanning external shift handover, unallocated cash, physical custody evidence, day-journal, supplier bank, patient invoice and period close; compare subledgers to GL with a finance reviewer.
- S5: restore a verified original V8.0 encrypted archive on a separate machine and reconcile opening balances, then obtain finance/medical/IT sign-off.

All new functionality beyond stabilization remains frozen until those P0 gates are evidenced. See `TEST_REPORT.md`, `DECISIONS.md`, and `ROADMAP.md`.

---

## Historical project record — preserved from S1 source

# G3D local status — 2026-11-01

- Branch: `feat/g3d-case-consumables-returns`, baseline G3C commit `2a5d2ee`.
- Scope: immutable original-lot FIFO returns (independent approval and reversing posted GL); net case costing; pending return month/case clearance blocking; direct SQLite defenses.
- Verified encrypted G3C source migration and rollback locally on synthetic fixture. Full final regression 120 = 114 PASS, 5 SKIP, 1 BLOCKED missing genuine V8.0, 0 FAIL; Separate CI 45/45 PASS exit 0; source-archive check tracked independently.
- No live database, hospital users, external push, deployment or real patient details. NO-GO.

Next 3: (1) complete regression+CI and reproducible source ZIP, (2) authorized physical return inspection/quarantine and corrected bills/PO/AP, (3) off-device restore and finance/clinical/IT UAT including missing genuine V8.0 source.

---

# G3C Project Autopilot verified state — 2026-10-31 (local source only)

- Baseline G3B commit `4933339`; local isolated branch `feat/g3c-case-consumables-cost`; NO production access or deployment.
- IMPLEMENTED: case-scoped approved FIFO consumables report with two independent access checks; pending/unlinked excluded; real Chromium query at 320/375/1440 with stale response replaced after revocation.
- IMPLEMENTED: chronological FIFO approvals check same-item later-approved issue by business date (API plus SQLite triggers). Deliberately keeps day-resolution same-day approvals in transaction order; no historical changes or new GL.
- IMPLEMENTED: frozen original G3B schema upgrade with authenticated encrypted `.rbe` pre-DDL backup, isolated restoration, no extra archive on a second start.
- Full source QA independently rerun: **116 scripts; 110 PASS / 5 SKIP unavailable history/private source / 1 BLOCKED missing V8.0 / 0 FAIL, 0 TIMEOUT.** See `QA_G3C_TEST_RESULTS.tsv` and technical report.
- CI smoke: **42/42 PASS (exit 0)** in `QA_G3C_CI_RESULTS.txt`. ZIP extraction and Git bundle verification are additional release gates reported independently.
- NO-GO production. Reports exclude drugs, unlinked supplies, opening stock, clinical salary, doctor fees, insurance and total case profit.

Next three:
1. Medical source issuance, per-case material returns/reversals and independently approved FIFO corrections, without historical silent mutation.
2. Vendor PO/invoice/AP, clinician billing governance, and insurer/doctor settlements.
3. Genuine V8.0 + historic G2J/G2K/G2L archives, external recovery/UAT, and finance/medical/IT signoff.

---

# G3B Project Autopilot verified state — 2026-10-31

- Git baseline: G3A `885e80e`; branch: `feat/g3b-clinical-document-fingerprint`; NO shared push or hospital deployment.
- IMPLEMENTED locally: independently attested source SHA-256/size/media, clinician signed-in upload/verification, department opt-in owner/password, SQLite immutable guards, invoice-time enforcement, migrated genuine G3A schema with pre-DDL encrypted backup, responsive pilot UI.
- Regression: 112 run, 106 PASS, 5 SKIP historic/private, 1 BLOCKED missing genuine V8.0, 0 FAIL, 0 TIMEOUT. Historical G2J/G2K/G2L `SKIP ` stdout corrected instead of falsely counted as PASS. See QA_G3B_TEST_RESULTS.tsv.
- Source file is transiently read and may be spooled to OS temp disk. No clinical source persisted in accounting tables. This is not evidence of professional licensing, validated source retention or legal signature.
- CI independent 39/39 PASS (exit 0); 3 Chromium browser test scripts PASS. Source-archive evidence will be recorded in `QA_G3B_RELEASE_VERIFICATION.txt` when issued.
- Production gate: NO-GO. Real off-device restore, medical/finance/IT signoff, professional licensing, secured HIS document custody, missing genuine historical source, complete case costing and hospital UAT outstanding.

Next three:
1. Independent medical identity/signature approval, clinical source custody policy, short-lived file/upload and privacy audit.
2. Governed remediation for historical unbilled reference-only/legacy viewer witnesses, with human audit and no silent DB rewrite.
3. Case-linked operating room/NICU consumables and suppliers/doctors/insurance subledger followed by independent hospital UAT and offsite restore.

---

# S4 integrated one-database financial day (2026-11-02, TEST_ONLY)

Baseline S3 `4e425e4`, isolated branch `stabilization/s4-integrated-day`. No production financial code, database schema, or hospital deployment modified. Implemented one source-owned `tests/test_s4_integrated_day.py` with actual patient invoice collection, external and internal tills, historical envelope reconstruction, supplier bank posting, approved bank statement, financial reconciliation and simulated month-end close.

Verified local acceptance: in-process single DB PASS; real Uvicorn HTTP same scenario PASS, 161 real TCP requests. Full regression 141 = 135 PASS, 5 SKIP, 1 BLOCKED_NO_V80; CI 66/66 PASS. Intermittent HTTP 500 during parallel QA load is not yet root-caused; 3 subsequent sequential 161-request runs passed. Real current-month close correctly blocked; only in-process test temporarily patches clock to exercise after-month seal. Original V8.0 and real hospital UAT unavailable. Release remains **DEVELOPMENT ONLY / NO-GO PRODUCTION**. Full CI and regression results belong to the S4 verification report, not inferred from this integration PASS.
