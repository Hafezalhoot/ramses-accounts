# GitHub Actions — وضع النقل S14

الـWorkflow السابق محفوظ للرجوع إليه في `docs/project-autopilot/qa-smoke.workflow.DISABLED.yml`، **وليس** تحت `.github/workflows/`، وبذلك لا يعمل عند الدفع للفرع `main` بهذه النسخة.

هذه الخطوة لا تغيّر إعداد GitHub على مستوى المستودع: عطّله أيضًا من GitHub → Settings → Actions → General قبل نشر أي فرع قديم. اختبارات CI قابلة للتشغيل يدويًا بالأمر `python scripts/ci_smoke.py` بعد إعداد بيئة Python المطابقة.

راجع `docs/project-autopilot/GITHUB_TRANSFER_2026-11-05_AR.md` وحالة `TEST ONLY / PRODUCTION NO-GO` قبل النشر.
