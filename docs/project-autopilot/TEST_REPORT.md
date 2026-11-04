# S13 — أحدث مرحلة موثقة / 4 نوفمبر2026 / TEST ONLY

استكمال من S12 `a4485e0` على `development/s13-cashier-printing`: حساب كاشير خارجي تجريبي، وفاتورة وإيصال وملخص وردية قابلون للطباعة بصلاحيات القراءة الأصلية، RTL/Cairo محلي، A4/80مم. نجحت رحلة الكاشير عبر HTTPS والمتصفح مع توثيق الخدمة واستلام واعتماد مستقلين بحسابات منفصلة. توجد حالتان جاهزتان للتدريب100 جنيه لكل حالة ووردية تالية برصيد بداية صفر.

**الدليل الحالي:**154 =149 PASS +5 SKIP، بلا FAIL/TIMEOUT/BLOCKED؛ CI78/78 PASS (جزء من المجموعة). ترحيل V8.0 الأصلي PASS. Chrome375/1440 وروابط الطباعة وPDF مرئية؛ لم تُختبر طابعة المستشفى. الأسرار والقاعدة خارجGit والحزمة؛ دليل الدخول محليًا `private/S13_CASHIER_ACCESS.txt`.

[تقرير المرحلة](S13_RELEASE_REPORT_AR.md) — [دليل الكاشير](S13_CASHIER_GUIDE_AR.md) — [التبديل بين Chat وWork](../../00_CONTINUE_IN_CHAT_OR_WORK_AR.md).

**PRODUCTION NO-GO:** FIN-01 بانتظار اعتماد رئيس الحسابات؛ ثم تكامل الاستحقاق والإقفال،2200 والمخازن والأطباء والتأمين والضرائب والأصول، الاستعادة المستقلة والمعدات وUAT واعتمادات المستشفى. لا يمثل اكتمال تجربة الكاشير اكتمال منظومة المستشفى. الأقسام التالية سجل تاريخي.

---

# S12 — أحدث تقرير اختبارات / 4 نوفمبر 2026

**153 =148 PASS +5 SKIP؛ صفر FAIL/TIMEOUT/BLOCKED؛ CI77/77 PASS.** المجموعة153 تشمل اختباراتCI، وليست مجموعتين مستقلتين.

التفاصيل الكاملة وأسباب الإخفاقات أثناء العمل وSKIP وحدود النتيجة في [S12_RELEASE_REPORT_AR.md](S12_RELEASE_REPORT_AR.md). أدلة الجولة في `evidence/S12/`، منها RED/GREEN للإصلاحات الثلاثة، و`final-full.tsv` و`final-ci.log` و`s12-http.log` و`integrated-http.log` و`external-browser-final.log`.

- الطلبات: إعلان زائد، أجزاء متعددة، stream دون طول أو بطول خاطئ، إغلاق الملفات الجزئية، قبول6MiB، وعدم أثر مالي للرفض.
- التخزين:503 دون إنشاءDB/مجلد، واستعادة المجلد الأصلي والجلسات معWAL/SHM، ومسار يحوي العربية و`#?`.
- الديمو: تهيئة عبرHTTPS داخلTestClient معSecure، وثلاث سندات وهمية وعدم تكرار.
- S12 الحقيقي عبرTCP:21 طلبًا؛ S4 اليوم المالي الموحد:161 طلبًا؛ مخططV8.0 الأصلي PASS ضمن المجموعة.
- Chrome375/1440 عبرHTTPS خارجي فعلي: حماية البوابة، دخول التطبيق، reload واستمرار الجلسة وSecure/HttpOnly وRTL/Cairo، دونoverflow أو أخطاءJS. نجح بعد معالجة حدود التوازي في بوابةApache؛ المحاولة الأولى الفاشلة محفوظة.
- فحص اعتمادياتPython: لا ثغرات معروفة في البيئة المثبتة وقتالفحص. لا يغطيApache أو نظامالتشغيل بالكامل.

المعاينة مؤقتة وعلى بيانات وهمية. لا يوجد ترحيل بيانات تشغيل أو افتتاح موقع، ولا اعتماد على معدات المستشفى أو قبول طبي/مالي/تقني أو سياسة إيراد موقعة. **PRODUCTION NO-GO.**

---

# S11 — تقرير الاختبارات الفعلي / 4 نوفمبر 2026

المصدر: `stabilization/s11-operational-review` من S10 `49167d9`. البيئة: macOS ARM64، Python 3.13.1، FastAPI 0.162.0، cryptography 50.0.2، pip 26.3، Playwright 1.64.1 مع Chrome مثبت. لقطة الإصدارات تشمل أدوات الاختبار والفحص في `evidence/S11/runtime-freeze.txt`. البيانات وهمية بالكامل.

جميع مسارات الأدلة التالية داخل `evidence/S11/`، ما لم يذكر خلاف ذلك.

| الفحص | النتيجة | الدليل |
|---|---|---|
| مطابقة التسليم | 607 بصمات سليمة، و596 ملف سورس مطابق لـGit | تقرير المراجعة ومصدر التسليم المحفوظ |
| أول مجموعة على S10 | 147 = 128 PASS و5 SKIP و14 FAIL | `baseline-full.tsv`؛ 12 مسار متصفح Linux واختبارا TCP ممنوعان داخل sandbox |
| المجموعة بعد إصلاحات S11 وقبل تحديث التشفير | 150 = 145 PASS و5 SKIP، صفر FAIL | `final-full.tsv` |
| **المجموعة النهائية بعد التشفير وتحسين عرض الموبايل** | **150 = 145 PASS و5 SKIP، صفر FAIL/TIMEOUT/BLOCKED، exit 0** | `final-secure-full.tsv` و`final-secure-full.log` |
| **CI النهائي** | **74/74 PASS، exit 0** | `ci-secure-final.log` |
| ترحيل V8.0 الأصلي | PASS؛ حفظ السند والحركة وحالة GL، وترقية متكررة واستعادة rollback مشفر | `v80-migration.log` ونتيجة المجموعة الكاملة |
| ذرية إنشاء البيانات الأساسية | RED ثم GREEN؛ يرجع المستخدم والموظف والخزنة وربط GL عند فشل audit | `atomic-red.log` و`atomic-green.log` |
| إقفال الحالة مع صرف معلق | RED ثم GREEN؛ حظر الطلب والاعتماد المتأخر وإتاحة الرفض المستقل | `case-inventory-red.log` و`case-inventory-green.log` و`case-inventory-regression.log` |
| استثناءات اليومية | RED ثم GREEN؛ نقص التسجيل والمراجعة والمواعيد القادمة وعدم الرصد ونطاق القراءة | `daily-exceptions-red.log` و`daily-exceptions-green.log` |
| Chrome يومية S11 | PASS على 375 و1440؛ RTL وتحميل Cairo فعلي، وبطاقات موبايل مقروءة دون تمدد أفقي أو أخطاء JS | `daily-browser-red.log` و`daily-mobile-cards-red.log` و`daily-browser-green.log` وصورتا الشاشة |
| Chrome تغطية الورديات | PASS كمبيوتر وموبايل، وفلاتر وحالة يوم بلا ورديات مطلوبة | `coverage-browser.log` |
| إصلاحات S11 عبر TCP محلي | PASS؛ ثلاثة خوادم وقواعد معزولة | `s11-http.log` |
| اليوم المالي الموحد S4 عبر TCP | PASS؛ 161 طلبًا يربط المريض والخزن والمورد والبنك والظرف القديم وGL | `integrated-http.log` |
| فحص التبعيات قبل التحديث | 19 سجل تحذير في حزمتين، يتضمن تكرارات | `dependency-audit.json`؛ cryptography 46.0.7 وpip 24.3.1؛ لا يثبت استغلالها عبر التطبيق |
| فحص التبعيات بعد التحديث | **لا ثغرات معروفة في البيئة المثبتة وقت الفحص، exit 0** | `dependency-audit-final.json` و`dependency-audit-final.log` |
| توافق النسخ المشفرة القديمة | PASS؛ إنشاء بـ46.0.7 واستعادة بـ50.0.2 مع تطابق المخطط وكل الصفوف منطقيًا | `crypto-backup-compatibility.log`؛ القاعدة والمفتاح الوهميان خارج الإصدار |
| سلامة الاعتماديات والصياغة | PASS؛ pip check وPython compile وNode check وفحص diff | `pip-check.log` و`syntax.log` |

## التجاوزات الخمسة

- `test_free_preview.py`: SKIP: private June historical workbook intentionally excluded from development ZIP
- `test_preview_modes.py`: SKIP: private June historical workbook intentionally excluded from development ZIP
- `test_v81e_g2j_schema_upgrade.py`: SKIP G2J G2I upgrade: original preceding source checkout unavailable
- `test_v81e_g2k_upgrade.py`: SKIP G2K historical G2J -> G2K upgrade: G2J source checkout not packaged
- `test_v81e_g2l_schema_upgrade.py`: SKIP G2L G2K source checkout not available; migration must be rerun with historical source

## إعادة التشغيل وحدود النتيجة

الأوامر في README_S11_AR.md. أُعيدت المجموعة الشاملة وCI بعد تحديث التشفير، وأُعيدت المجموعة الشاملة والاختبار المرئي بعد تحسين بطاقات الموبايل. العدد يحصي سكربتات، ولا يمثل تغطية الأسطر أو الفروع. CI مجموعة فرعية من الاختبارات الشاملة وليست 74 اختبارًا إضافيًا مستقلًا عنها.

اختبار Chrome اليومي يمرر الطلبات إلى ASGI وSQLite حقيقيين عبر جسر اختباري. مشغلا S11 وS4 يختبران TCP/HTTP محليًا في عمليات Uvicorn مستقلة. لا توجد نتيجة HTTPS أو شبكة مستشفى أو طابعة فعلية أو توقيع طاقم أو حمل وفق SLA معتمد.

ظهرت رسالة إهمال من Starlette عن استخدام httpx داخل TestClient؛ لم تسبب فشل الاختبارات، وتستلزم متابعة توافق أداة الاختبار مستقبلًا. بناء Docker/Linux غير منفذ هنا. فحص الثغرات يتعلق بالاعتماديات المثبتة وقت الفحص، ولا يغلق عيوب التطبيق الأمنية المفتوحة.

لم تطبق سياسة الاستحقاق المقترحة، ولم يحل عيب FIN-01. لا توجد هجرة مخطط جديدة ضمن S11. اختبار V8.0 يستخدم مخططًا أصليًا مع بيانات وهمية؛ لا يوجد ترحيل قاعدة تشغيل أو توقيع أرصدة افتتاحية. **الحالة: TEST ONLY / PRODUCTION NO-GO.**

---

# S10 synthetic acceptance (2026-11-02)

**RED evidence:** original `/api/shifts/day-summary` returned `shift_coverage_complete=false` for `[{'status':'complete'}, {'status':'not_required'}]`; the new synthetic API test failed at that exact field. After code fix the S10 direct acceptance passes, preserving not-monitored/missing/zero-required blocks and zero GL/fund/audit read side effects. Browser test for new off-day label passes at Chromium 1280/375 after fixing a stale October 2026 fixture. CI/full source QA and integrated financial day results are recorded when finished. No original V8.0 archive or real hospital workstation tested.

**Final source verification:** CI `python scripts/ci_smoke.py` **71/71 PASS** exit 0. Full regression `python scripts/qa_g2t_full.py` **147 scripts: 141 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT** exit 0. Existing S4 integrated finance across independent Uvicorn HTTP **161 requests PASS** (cash 1850, supplier 40, bank 140 EGP; balanced synthetic GL); S9 Uvicorn HTTP **33 requests PASS**. S10 synthetic authenticated HTTP TestClient PASS with off-day / missing / zero-required / unknown distinctions, no ledger writes; Chromium at 1280/375 PASS. These do not represent hospital device/LAN/HTTPS acceptance.

---

# S9 - date-aware shift-opening option QA (2026-11-02)

**RED:** `tests/test_s9_shift_open_options.py` returned HTTP 404 because the read-only route did not exist. Browser selection used the newest station plan even for an earlier business date. Both were independently reproduced before production edits.

**GREEN targeted:** TestClient PASS on current/future versions, per-clerk `allowed_codes`, viewer/unassigned/protected-fund denial, closed weekday, future POST denial and zero GL/cash/audit read effects. `scripts/qa_s9_http.py` PASS **33 genuine local Uvicorn HTTP requests**; `tests/browser_s9_shift_open_options_offline.py` PASS 1280/375 with date/fund switching, future/empty disable and stale response rejection. S8 historical names and S2 financial cycle remain PASS. Full CI/QA outcomes in the S9 release report; original V8.0 migration is still **BLOCKED**, not a PASS.

**Final source-wide verification (S9):** `python scripts/ci_smoke.py` completed **70/70 PASS**, exit 0. `python scripts/qa_g2t_full.py` completed **146 scripts: 140 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT**, exit 0; the historical fixture was unavailable and remains unverified. Independent `S4_REAL_HTTP=1 python tests/test_s4_integrated_day.py` PASS 161 real local TCP HTTP requests, balanced ledger with 1850 EGP central vault, 40 EGP supplier AP, 140 EGP synthetic bank. Original S9 real TCP HTTP **33/33**, and Chromium 1280/375 **PASS**. No actual hospital deployment or real patient financial data.

**S9 final verification on source `stabilization/s9-date-aware-shift-creation`:**
- CI `python scripts/ci_smoke.py`: **70/70 PASS, exit 0**. Source file `QA_S9_CI_RESULTS.txt`.
- Complete `python scripts/qa_g2t_full.py`: **146 scripts: 140 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT, exit 0**. Source `QA_S9_TEST_RESULTS.tsv` and `QA_S9_FULL_SUMMARY.txt`. Historical original V8.0 archive is unavailable; **blocked is NOT PASS**.
- S9 authenticated HTTP via local independent Uvicorn: **33 requests PASS**; Chromium fixture at 1280/375: PASS; S2 and S8 direct regressions: PASS.
- S4 shared synthetic financial day with independent Uvicorn TCP: **161 requests PASS**; central cash 1850 EGP, supplier 2200 remaining 40 EGP, bank 140 EGP; GL balanced.
- Python compilation and JS syntax `node --check`: PASS. No production deploy, real patient data, bank actions, HTTPS or on-site UAT.

---

# S8 - effective-dated historical cashier names (2026-11-02)

**Release state: TEST_ONLY; PRODUCTION NO-GO.** Base S7 `67cbdf8`, isolated branch `stabilization/s8-historical-shift-identity`. No SQLite schema, posting amounts, patient data, hospital deployment or grants modified.

**RED evidence:** `tests/test_s8_historical_shift_identity.py` failed when `/api/shifts` lacked an effective-dated historical name after a new future schedule; dedicated per-shift daily report test also failed. Offline Chromium reproduced mislabeling from the current/latest schedule in desktop, 375px mobile and day/daily modal. Existing older browser test failed because 2026-10 fixture was loaded with default 2026-11 month; corrected fixture, not business logic. See `s8_*_red.txt` in working QA session (non-release debug artifacts).

**GREEN changes:** `cashier_ops.historical_shift_name` resolves name from the schedule version valid on session business date for linked cashier point, with legacy code fallback; `app.py` returns `shift_name` on shift list, hospital day summary and per-shift daily report; `static/app.js` uses read-only historical names on those four surfaces with `esc` HTML encoding. New-shift option configuration remains separate. Historic session `shift` code and money records stay unchanged.

**Actual checks:**
- `python tests/test_s8_historical_shift_identity.py`: PASS, one disposable SQLite / API with future rename, denied viewer access, zero GL/fund/audit writes and SQLite integrity.
- `python scripts/qa_s8_http.py`: PASS, separate local Uvicorn process, **11 real HTTP requests** (not HTTPS/hospital LAN). Evidence `QA_S8_HTTP_RESULT.txt`.
- `python tests/browser_s8_shift_history_offline.py`: PASS Chromium 1280 and 375px, day and individual modals; no JavaScript errors or mobile horizontal overflow. This uses synthetic browser fetch fixtures, not end-user network.
- `python tests/browser_shifts_render_offline.py`: PASS after pinning source's historical test fixture month explicitly.
- `python tests/test_s2_cashier_24h_acceptance.py`, `python tests/test_s4_integrated_day.py`, `python tests/test_v82_g2w_shift_fund_scope.py` and shift coverage: PASS, account reconciliation invariants unchanged.
- `S4_REAL_HTTP=1 python tests/test_s4_integrated_day.py`: PASS on *final S8 source*, **161 real TCP HTTP requests**: patient and cashier 600 EGP, historical envelope net 1300 EGP, central expense 50 EGP, vault 1850 EGP, supplier AP 40 EGP and bank 140 EGP, balanced GL. Recorded in `QA_S8_S4_HTTP_RESULT.txt`.
- **Fresh full CI** `python scripts/ci_smoke.py`: **69/69 PASS**, exit 0; 1 additional S8 source-owned regression included.
- **Fresh complete source regression** `python scripts/qa_g2t_full.py`: **145 files = 139 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT**, exit 0. The original V8.0 migration is blocked and *not* included in the passes. Five test skips remain explicit. Original `QA_G2T_TEST_RESULTS.tsv` kept in its prior baseline; full S8 outcome preserved in `QA_S8_TEST_RESULTS.tsv`.

**Not done:** authentic V8.0 archival migration and opening balances; recovery on a physically separate workstation; actual browser over TLS/hospital LAN/printers/payment terminals; signed independent finance/medical/IT UAT; external penetration assessment. No production GO decision is defensible from local synthetic test counts.

---

# S7 — local offline recovery rehearsal acceptance (2026-11-02)

**Verified suite on S7 final source:** CI 68/68 PASS; full regression 144 = 138 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT; S4 separate Uvicorn 161 requests PASS; `QA_S7_*` source evidence. Neither real external machine recovery nor genuine V8.0 historical migration was performed.

S7 `tests/test_s7_recovery_drill.py`: demonstrated RED before CLI (`scripts/recovery_drill.py` missing) and GREEN after tool implementation, using only a synthetic encrypted archive. Positive SHA256, AES-GCM authenticated restore, immutable financial checks inherited from S6, separate-process FastAPI health 200 and unauthenticated `/api/me` 401 on disposable DB copy. Negative cases: wrong SHA, wrong key, tampered ciphertext with independently matching transport hash, existing output dir, symlink and missing archive all rejected. Additional RED→GREEN found an archive substitution race between initial SHA check and decrypt; S7 now binds both to one privately staged copy, rejecting a substituted validly AES-encrypted second archive. Expected report has no sensitive contents. Cross-device IT test: **NOT PERFORMED**. See per-release QA results for CI/full suite outcomes.

---

# S6 — Financially safe encrypted backup and simulated independent restoration (2026-11-02)

**S5 baseline:** `38b2720e175f4f8b4895074355d47d0b3ade64bd`, S6 branch `stabilization/s6-recovery`; **TEST_ONLY / PRODUCTION NO-GO**.

**RED observed:** A posted GL journal modified to have debit 12000 and credit 11999 piasters passed SQLite `integrity_check` and `foreign_key_check` on original S5 verifier. The regression expected rejection, but it failed. A separately constructed case with a missing `gl_no_posted_line_update` trigger also passed the original verifier.

**GREEN implemented:** `scripts/secure_backup.py` now rejects unbalanced posted GL, mismatched evidentiary BLOBs or recorded byte lengths in voucher/cashier evidence and bank CSV sources, and absent principal financial SQL immutability triggers for current schemas. It rejects creation/publication of a corrupt snapshot and refuses verifying/restoring an already-encrypted but logically corrupt synthetic archival backup. No change to AES-GCM format, schemas, account rules or application API.

**Independent logical recovery QA:** `tests/test_s6_backup_financial_integrity.py` PASS. Synthetic valid GL and source BLOBs encrypted to `.rbe`, copied to a logically separate directory, key kept in a separate private path, recovered using a new Python process, SHA-256 row fingerprint equality over ten sensitive tables (including evidence bytes), 0600 file and successful app login on recovered DB; second restore refused. This was a **same-host multi-directory test, not a second physical device**.

**Fresh full CI:** `python scripts/ci_smoke.py` **67/67 PASS**, exit 0; new S6 regression included. Baseline G2M encrypted restore regression PASS. Python compileall, JS node syntax checks and Git whitespace check PASS.

**Financial workflow unchanged:** S4 in-process single-DB integrated day PASS; S4 separate Uvicorn TCP HTTP PASS **161 requests** with cash 1850 EGP, supplier AP 40 EGP and bank 140 EGP, balanced GL. HTTP was loopback, not TLS, browser or hospital LAN.

**Not completed:** S6 source-wide 141+ script QA sweep; original V8.0 authentic migration (archive absent); real off-device restore; hospital HTTPS/browser/printers/terminals; clinical/finance/IT signoff and data protection review. No live data, payments, migrations or deployment changed. **Production NO-GO.**

---

# S5 — Source-first FastAPI / SQLite contention correction (2026-11-02)

**Baseline S4 branch**: `60bddc1`. One isolated temporary SQLite database per independent test. Real Uvicorn HTTP over loopback, no TLS/browser/hospital dataset.

**RED 1 (S4 unmodified `bootstrap.connect`)**: 96 concurrent authenticated HTTP point-assign requests, 16 workers; 14 HTTP 200 / 65 HTTP 500 / 17 network failures. Server traceback: `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread` at billing `assign_point`. 15 audit entries despite 14 acknowledged successes, demonstrating ambiguous outcomes to clients.

**GREEN 1**: `check_same_thread=False`, per-request connection retained. 240/240 at 24 workers, 256/256 at 32 workers, no 500.

**RED 2**: 384 HTTP assignments, 48 workers; 383 HTTP 200 / 1 HTTP 500. Trace `sqlite3.OperationalError: database is locked` at `BEGIN IMMEDIATE`; 10s `PRAGMA busy_timeout` contradicted sqlite3 connection's 30s timeout.

**GREEN 2**: Remove redundant PRAGMA, inherit `timeout=30` => SQLite busy_timeout 30000ms. Final 384/384 HTTP 200, 384 audit events, 12 unique active permissions, 403 denied clerk reassignment, `integrity_check=ok`, zero FK violations. Final p50 0.680s, p95 4.818s, worst 10.035s. These timings depend on this isolated test machine and are not a hospital SLA. Another 384/48 run with explicit 30000 PRAGMA also passed, followed by a 240/24 after simplification.

**S4 integrated day post-final code**: in-process PASS; separate Uvicorn real TCP HTTP PASS 161 requests, patient/cashier, central vault, supplier, bank, GL, protected period-close gate unchanged.

**Eight sensitive regression scripts independently PASS**: `test_user_lifecycle.py`, `test_v82_g2t_concurrency.py`, `test_v82_g2t_revocation_race.py`, `test_v81e_g2j_treasury_integrity.py`, `test_v81e_g2i_financial_safety.py`, `test_v81e_g2m_secure_backup.py`, `test_v82_g2q_security.py`, `test_v82_g2w_gl_viewer_scope.py`.

**Full CI is NOT GREEN IN S5**: `python scripts/ci_smoke.py` hit container execution timeout after 240s; first five lines PASS and no observed FAIL, remaining results unknown/uncompleted. No full S5 141-script QA run executed. Prior S4 full suite evidence cannot substitute for current commit.

**Production NO-GO**: original V8.0 not sourced, no independent off-device restore, network/TLS/browser/workstations not exercised, real employee signoff and financial/medical procedures unapproved. No real monetary or hospital data used.

---

# S4 verified synthetic integrated financial-day acceptance (2026-11-02)

**Status: DEVELOPMENT TEST_ONLY / HOSPITAL PRODUCTION NO-GO.** Source S3 baseline `4e425e490d027922e8b4ab5f43d7aa0c4a2c874f`. Isolated branch `stabilization/s4-integrated-day`. No financial backend, GL rules, schema, production records or deployments altered. A single source-owned synthetic test was added.

## Executed tests and evidence

- `python tests/test_s4_integrated_day.py`: PASS. Same disposable SQLite database connects real patient invoice/collection, night/morning/evening cashier handover, central treasury, historical sealed envelope correction, supplier PO/GRN/invoice and due schedule, independent payment and statement signoff, 2200 attributed payables, GL, bank, and period preflight.
- `S4_REAL_HTTP=1 python tests/test_s4_integrated_day.py`: PASS. Same scenario over a separate Uvicorn HTTP listener on 127.0.0.1 using distinct `requests.Session` cookies; **161 actual HTTP requests**, NOT Chromium, browser, TLS or hospital network.
- Three further sequential repeat runs of the same HTTP test: **3/3 PASS, 161 requests per run**. Their logs are separately captured in test-session QA evidence.
- Full regression `python scripts/qa_g2t_full.py`: 141 total scripts, **135 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT**, exit 0. These are scripts, not branch/statement coverage. Full TSV captured separately.
- `python scripts/ci_smoke.py`: **66/66 PASS**, exit 0. Historical original V8.0 test NOT covered. Detailed CI output captured separately.
- S4 negative gates: denied a cashier self-handover, denied cross-role transfer, rejected altered retry key, unmatched bank statement before signing blocks period close; after signing, settlement confirmation reaches 6000 piasters and 4000 remain as supplier 2200 payable. Real current month close stays HTTP 409. A **test-process-only** simulated future clock proves completed prior-month close, never applied to the HTTP worker or any production instance.

## Accounting result (synthetic, Egyptian pounds)

- Current-day external cashier receipts: 100 real patient invoice + 200 + 300 = **600**. External cash fund ending balance **0** after three independent deposits.
- Historical signed-paper-only invoice 1,500 minus previously cash-paid expense 200 = **1,300** physically received once in current central treasury. Prior closed GL/fund movements unchanged.
- Central real expense 50 yields **1,850** physical central treasury, independently matched; one 100 supplier liability with 60 approved from bank gives **40** remaining 2200 supplier AP; bank starts at 200 and ends at **140**.
- Patient reconciliation and cash/treasury reconciliation both report matched, GL debit=credit, no SQLite integrity or FK errors. These totals reflect one synthetic database, not hospital day-end signoff.

## Known irregularity; not hidden

During **concurrent parallel suite load**, one real HTTP rerun received **500** on the cashier point assignment request early in fixture setup. The source of this intermittent response was not reproducible after the parallel load ended: three sequential 161-request reruns all passed and no financial mismatch was observed. **Root cause NOT ESTABLISHED; do not claim it fixed.** Before real load/UAT, reproduce under deliberate concurrent load with persistent Uvicorn trace output and resolve any actual server error. This is a separate load/resilience gate, not evidence of financial corruption.

## Strictly NOT verified

Original verified V8.0 migration and signed opening balances, independent encrypted **off-device** restore, browser-to-HTTPS through reverse proxy and hospital workstation/network, printers, real money/source documents, medical policy, supplier 2200 month-close inclusion policy, security pen-test and MFA/IdP, finance/clinical/IT signatures. No live system was changed. **Production NO-GO**.

---

# S3 - local real-HTTP proof (2026-11-02)

Source: S2 commit `3e9669229b5ecc3da954416c1a541ff8642ea71c`.
The browser still cannot reach local HTTP (administrator policy), therefore
S3 uses independent `requests.Session` clients to a separate Uvicorn process,
not mocked/TestClient transport. All DBs are ephemeral SQLite with synthetic
funds, users, invoices, shifts and evidence.

## Direct S3 real HTTP results

- cashier_day: PASS; 4 independent shifts, 600 EGP external, 50 EGP central
  expense, 550 EGP main; detailed reports match and outsiders denied.
- deposit_retries: PASS; same request key and two parallel HTTP retries
  produce one voucher; changed amounts/other physical key rejected.
- late_invoice: PASS; old closed-month evidence links to a current-period
  invoice/GL; no fictional historical cash.
- mixed_envelope: PASS; 4500 gross patient invoices, 600 old paper expenses,
  3900 net physical cash, +/-50 EGP tracked in suspense, no double cash.
- http_security: PASS; separate cookies and active CSRF required, 401/403,
  HttpOnly/SameSite Strict, role denial, static HTML/JS through real HTTP.

**Five independently isolated HTTP suites passed (5/5, exit 0)**. See the committed
`QA_S3_HTTP_RESULTS.txt` for source-own outputs and HTTP request counts.
This does not establish real hospital finance signoff or actual TLS/browser
network readiness. Original Chromium loopback attempt still blocked.

## Additional checks

- Updated S2 daily report assertions passed using TestClient and Uvicorn HTTP.
- `python scripts/qa_g2t_full.py`: 140 scripts; 134 PASS + 5 SKIP + 1
  BLOCKED_NO_V80, zero FAIL/TIMEOUT; exit 0. Full source output is
  `QA_S3_TEST_RESULTS.tsv` and `QA_S3_FULL_SUMMARY.txt`.
- `python scripts/ci_smoke.py`: **66/66 PASS (exit 0)**, retained in
  `QA_S3_CI_RESULTS.txt`; historical V8.0 migration remains unverified.
- Counts represent executed test scripts, NOT statement/branch coverage.
- V8.0 original migration, off-device restore, TLS/real browser, clinical
  authenticity and real 24h UAT are explicit **NOT VERIFIED** gates.

---

# S2 verification and evidence (2026-11-02)

## Starting state

- Verified original G3N-S1 ZIP SHA-256 `8287690bd1f69b3f93566a169b14e9c28d09fb3086baf72feca51cda724e670c` and Git bundle SHA-256 `8788d7f122e05ebab06d8f2e47686e47004a31973e40b9a3a4a414332dc98893`.
- Checked out new branch from commit `1c35cb57812b0cde6670b7d1a5e3f07c95e550be` rather than modifying source baseline.

## Executed locally on disposable SQLite

- `python tests/test_s2_cashier_24h_acceptance.py`: PASS (4 closed shifts, 600 EGP deposits, 50 EGP central expense, 550 EGP balance, source 0, one revenue recognition and balanced GL, integrity/FKs).
- `python tests/test_s2_treasury_retry.py`: PASS (initial same-key duplicate produced two vouchers **before fix**; after fix same-key replay returns one, changed amount/wrong identity/changed key with same physical reference rejected 409, simultaneous two-thread retry produced one voucher).
- `python tests/browser_s2_cashier_treasury_ui.py`: PASS, 375 px and 1440 px, real Chromium DOM and JavaScript with browser fetch bridged into REAL FastAPI TestClient/SQLite, two additional positive deposits. No horizontal overflow, no page JS errors. Previously `undefined` shift clock assertion failed and now passes.
- `python tests/test_v81e_p3_main_treasury.py`: PASS (historical external-to-central and settled variance/ledger).
- `python tests/test_v81e_p4_shortage_repayment.py`: PASS (historic 6+4 settlement, immutable records, GL).
- `node --check static/app.js`: PASS.
- `git diff --check`: PASS.

## Wider regression

- `python scripts/qa_g2t_full.py`: **two independent complete runs, each exit 0**: 140 scripts, **134 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT**. After final code changes direct S2 and historic treasury scripts passed again. This runner uses `SKIP` for missing predecessor fixtures; it never equates them with passes.
- `python scripts/ci_smoke.py`: **66/66 PASS (exit 0)**. Historical V8.0 migrations are explicitly excluded.
- Browser network HTTP, TLS/reverse-proxy, actual hospital deployment, real banking credentials, V8.0 original upgrade, off-device restore, certified UAT: **NOT EXECUTED**.

Synthetic source screenshots can be found in separate release bundle. All accounts, staff, amounts, bank funds and transactions are artificial.

---

## Historical project record — preserved from S1 source

# G3D final local full QA — 2026-11-01

- Branch `feat/g3d-case-consumables-returns`, 120 unique scripts invoked: **114 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL, 0 TIMEOUT**. Source `/mnt/data/QA_G3D_TEST_RESULTS.tsv`. Full runner exit code 0.
- G3D TDD: immutable original-lot independent physical returns (2 at 1200 piasters = 2400 piasters net decrease); authorization/Idempotency/FIFO as-of dates/month close/financial-case pending closure/double request concurrency/direct SQL; encrypted frozen G3C upgrade/restore; responsive Chromium 1440/375/320.
- Existing legacy tests for billing service day, physical cash movements and daily shift coverage failed at Cairo midnight due UTC/no grace context. Corrected **tests only** and individually reran each 3/3 PASS; final entire suite rerun clean. Original first-run failures are not reclassified into passes retroactively.
- Separate CI suite 45/45 PASS exit 0 (`QA_G3D_CI_RESULTS.txt`); exact extracted ZIP verification remains independently recorded in release report. NO production approval, no offsite restore and no genuine V8.0 source.

---

# G3C QA regression — 2026-10-31

- Real FastAPI RED→GREEN: missing case cost route 404 -> approved two-lot 5600-piaster trace, dual grants and immediate revocation, no patient names or extra GL.
- Real API+SQLite RED→GREEN: historical-date receipt/issue approval incorrectly accepted -> 409 on API and SQLite direct SQL protection, with no new GL or stock allocations after rejection.
- Real Chromium RED→GREEN: missing case-cost search -> responsive 1440/375/320 retrieval and stale-result removal after permission denial.
- Frozen exact G3B SQL: requires encrypted rollback before two new SQLite triggers, restores original schema and users/sessions/stock, no duplicate backup on restart.
- Complete fresh suite: 116 invoked; **110 PASS / 5 SKIP / 1 BLOCKED original V8.0 / 0 FAIL / 0 TIMEOUT**, exit 0. Unexecuted predecessor tests and private workbook tests are not counted as PASS.
- CI smoke independently: **42/42 PASS (exit 0)**. Local source only, not end-user/hospital acceptance. `QA_G3C_TEST_RESULTS.tsv` is the detailed evidence file.

---

# G3B — local synthetic full regression (2026-10-31)

- **112 individual scripts invoked:** 106 PASS, 5 SKIP, 1 BLOCKED_NO_V80; **0 FAIL**, **0 TIMEOUT**. Full stdout-derived report: `QA_G3B_TEST_RESULTS.tsv`.
- 3 historical G2J/G2K/G2L files printed `SKIP ` without colon and returned exit 0; initial runner misclassified as PASS. We audited their captured stdout, re-ran each and corrected all 3 to SKIP. 2 other source-private Excel tests SKIP; genuine V8.0 original archive missing, blocked.
- TDD API: document hash computed from synthetic PDF bytes, owner opt-in/password and blocked old unbilled witnesses, invalid PDF/size/mime, row immutability, direct SQLite insert guard, invoice gate, revoke mid-session, hash match mismatch and audit metadata no-source.
- Genuine G3A fixture upgrade: encrypted rollback key required before DDL, frozen witness IDs and sessions intact, restored prior schema independently.
- Chromium pilot (stubbed synthetic backend) at 320/375/1440 demonstrates uploaded clinical form and owner opt-in; no EHR/HIS integration or legal medical acceptance.
- CI result separately executed: 39/39 PASS, exit code 0; `QA_G3B_CI_RESULTS.txt`. Three independent Chromium scripts PASS; `QA_G3B_BROWSER_RESULTS.txt`.
- NOT EXECUTED: real hospital UAT, genuine V8.0 upgrade, three pre-G3A historical source snapshots, third-party medical registration, original file custody service, off-device restore or live deployment.
