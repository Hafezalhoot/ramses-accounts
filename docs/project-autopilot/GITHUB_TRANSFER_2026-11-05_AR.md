# تسليم S14 إلى GitHub — نسخة نقل فقط

**الحالة:** جاهزة للنقل محليًا، **وليست منشورة على GitHub بمجرد إنشاء الحزمة**.

- المستودع المستهدف: `Hafezalhoot/ramses-accounts` (Private).
- المصدر: حزمة `Ramses_All_Project_GitHub_Transfer_2026-11-05_TEST_ONLY.zip`.
- آخر Commit وظيفي قبل تجهيز النقل: `c408e07589a7d46602044273c6a8c0848469b3cc`.
- تم الحفاظ على كامل تاريخ Git وتواريخ المراحل والـBranches الستة محليًا.
- **تعطيل GitHub Actions على مستوى المصدر:** نقل `qa-smoke.yml` من `.github/workflows/` إلى `docs/project-autopilot/qa-smoke.workflow.DISABLED.yml`؛ لا يوجد Workflow نشط في رأس `main`. الاختبارات تبقى متاحة يدويًا عبر `python scripts/ci_smoke.py`.
- **تعطيل إعدادات المستودع نفسه:** يتطلب Settings → Actions → General → Disable Actions، أو `gh api` بمصادقة إدارية. لا يُعتبر ذلك مكتملًا إلا بعد التحقق من إعدادات GitHub. رفع فروع تاريخية قد تحتوي على Workflow قديم ممنوع قبل التحقق من التعطيل على مستوى المستودع.
- لا يتم تضمين `.env` الحقيقي أو قواعد البيانات والتخزين والنسخ الاحتياطية وبيانات المرضى أو كلمات المرور. استخدم `.env.example` لإعداد بيئة اختبار جديدة بأسرار محلية.
- **التشغيل الحقيقي غير مصرح:** TEST ONLY / PRODUCTION NO-GO؛ مطلوب استكمال التأمين، الذمم، دفاتر المرضى، دورات المستحقات، قبول المالية/IT/الإدارة الطبية، واختبارات ميدانية واستعادة مستقلة.

## قبل الدفع

1. افتح صفحة Settings → Actions → General للمستودع وعطّل Actions لتأمين الفروع التاريخية.
2. افحص مصدر الشيفرة المرفق وتأكد من أن `git status` نظيف وأن `git ls-files .github/workflows` لا يعرض أي Workflow.
3. شغّل ملف Mac المرفق في مجلد النقل أو نفّذ `git push -u origin main` بعد توثيق GitHub؛ دون Force Push.
4. بعد نجاح الدفع تأكد من تطابق `git rev-parse main` مع `git ls-remote origin refs/heads/main` ومن ظهور الوثائق والاختبارات ومجلد `static`.
5. لا تنشر الفروع التاريخية إلا بعد تأكيد أن إعداد Actions بالمستودع `enabled=false`، حتى لا تعمل ملفات Workflows القديمة فيها.

## اختبارات قبل المعاينة

- فحص ملفات Git: `git fsck --full --no-reflogs`
- فحص صياغة الكود: `python -m compileall -q app.py bootstrap.py scripts tests`
- المجموعة المالية الآلية: `python scripts/ci_smoke.py` بعد تثبيت `requirements.txt` في بيئة معزولة.
- المعاينة: استخدم `compose.yaml` في جهاز/خادم اختبار منفصل وبيانات وهمية وHTTPS وحماية مصادقة، وليس Vercel Serverless الافتراضي لأنه لا يوفر ملف SQLite دائمًا بهذه البنية.

المرحلة التالية بعد وصول الكود إلى GitHub: مقارنة SHA والملفات؛ تشغيل CI خارج GitHub Actions دون بيانات حقيقية؛ تجهيز بيئة Staging مؤقتة مع قاعدة اختبار جديدة؛ اختبارات المتصفح؛ ثم خطة معالجة ثغرات التشغيل. لا يُسمح بنشر Production تلقائيًا.
