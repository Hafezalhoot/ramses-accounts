# GitHub Actions — سجل النقل التاريخي S14 ثم الاستعادة الآمنة

## ما حدث عند النقل (سجل تاريخي)

الـWorkflow القديم محفوظ في `docs/project-autopilot/qa-smoke.workflow.DISABLED.yml`، وكان قد أُزيل من `.github/workflows/` على `main` ضمن تأمين استيراد المستودع. وعُطلت GitHub Actions على مستوى إعدادات المستودع قبل رفع الفروع التاريخية.

## ماذا أُضيف بعد ذلك؟

يحتوي فرع `infra/ci-python313-isolated-gates` على workflow جديد مستقل باسم `.github/workflows/finance-ci.yml`، وبوابة `scripts/ci_audit_gate.py`، لا ينشر التطبيق ولا يصل إلى قاعدة المستشفى. يُنفذ Python 3.13 بصلاحية قراءة فقط، مع تاريخ Git كامل واختبارات على بيانات صناعية. هذا لا يعني أنه نُفذ على GitHub بالفعل.

**لا يزال تفعيل Actions من إعدادات GitHub والتحقق من أول تشغيل فعلي خطوة منفصلة لصاحب المستودع.** اقرأ `docs/project-autopilot/CI_SAFE_ENABLEMENT_AR.md` قبل التفعيل. الفروع التاريخية قد تحتوي على Workflows أقدم غير مقيدة، فلا تُجرِ push عليها للتجربة.

**TEST ONLY / PRODUCTION NO-GO**: نجاح CI، عند حدوثه، ليس موافقة على مالية أو طبية أو تشغيل مستشفى فعلي.
