# GitHub Actions — قرار المالك: تبقى معطلة للمستودع الخاص

أثناء نقل S14 إلى GitHub، تم تعطيل GitHub Actions على مستوى المستودع وحذف ملفات التشغيل النشطة من الفرع الرئيسي. **المالك أكد في 5 نوفمبر 2026 أنه لا يريد إعادة تشغيل GitHub Actions لأنها تستهلك رصيد التشغيل في المستودع الخاص.**

## ما نعتمده بدلًا منها

- GitHub: حفظ السورس وتاريخ Git والفروع وPull Requests، دون تشغيل اختبارات على GitHub-hosted runners.
- Work أو جهاز موثوق: تشغيل فحوص Python 3.13 وGit وNode من نسخة كاملة للتاريخ، باستخدام `python scripts/run_local_qa.py --full`.
- تقرير مرتبط بالـCommit وبنتيجة كل بوابة، مع فصل `PASS` و`SKIP` و`BLOCKED`. لا اعتماد تشغيل حقيقي من نتائج صناعية.
- ملف التشغيل القديم محفوظ تاريخيًا ضمن `docs/project-autopilot/qa-smoke.workflow.DISABLED.yml`. **لا يوجد ملف Workflow نشط مطلوب ولا تُنشئ واحدًا دون موافقة جديدة صريحة.**

راجع: `docs/project-autopilot/CI_NO_ACTIONS_WORKFLOW_AR.md` و`AGENTS.md`.

**تنبيه:** فروع التطوير التاريخية قد تحتوي على Workflows قديمة؛ لا تفعّل Actions للمستودع أو تدفع إليها فقط لتجربة اختبارات. لا تُفترض نتائج اختبارات آلية في واجهة GitHub. يبقى المشروع `TEST ONLY / PRODUCTION NO-GO`.
