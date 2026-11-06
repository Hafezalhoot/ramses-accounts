# تطوير رمسيس عبر أي مساعد — السياسة النشطة6 نوفمبر2026

وافق المالك على Public بعد فحص119commit و12فرعًا وكل الصور/PDF/البيانات والمحادثات، وأكد أن أدلة المعاينة وهمية. يسمح بتفعيل GitHub Actions وRulesets والدمج المصرح به بعد اختبارات فعلية. المستشفى تظل TEST ONLY /PRODUCTION NO-GO. تعليمات no-Actions السابقة سجل تاريخي.

## المسار المعتاد

1. أي مساعد يملك اتصال GitHub وصلاحياته الشرعية يقرأ AGENTS/حالة المشروع وآخر PRs، ويعمل في فرع مستقل.
2. افتح PR إلى main؛ Actions يشغل ramses-security وramses-core-ci على SHA الرأس المحدد، Python3.13 وChromium/Playwright واختبارات المحاسبة والصلاحيات والواجهة. لا تبنِ قرارًا على SHA أقدم.
3. راجع الفرق ونتائج الاختبارات والاستثناءات. يحدث المساعد الفرع إذا تغير main، ثم يعيد التحقق.
4. عند النجاح يسمح المالك لأي مساعد مخول بالدمج؛ Rulesets تبقى الحكم الخادمي، دون فرض موديل أو مراجع AI بعينه. من trusted main نظيف: `python3.13 scripts/qa_checked_merge.py --pr N` ثم `--merge` للدمج الصريح عند استيفاء الشروط.

## حدود الأمان

الـworkflow على pull_request وpush إلى main وworkflow_dispatch، صلاحياته contents:read فقط ولا references إلى secrets. لا pull_request_target أو self-hosted runner. checkout بدون حفظ credentials، Actions مثبتة بـ40حرفSHA، وفحص Gitleaks مثبت ببصمة الإصدار. الاستثناءات محصورة في commit/path تاريخية سبق تدقيقها؛ SHA جديد يبقى مفحوصًا. الملخصات المرفوعة أعداد وحالات وSHA فقط، دون raw logs/TSV/fixtures أو قواعد بيانات.

Docker API ينقل نسخة المصدر إلى volume مؤقت في RAM، دون host binds أو GH_TOKEN أو Docker socket. root read-only، networknone، cap-drop ALL، no-new-privileges، UID غيرroot وحدودCPU/RAM/PID. تقرير TSV السابق يحذف قبل التشغيل؛ symlink/تقرير ضخم أو تغطية ناقصة تفشل. GitHub-hosted runner مؤقت حتى للـforks؛ أسرار المستودع لا تُمرر إليها. PRs من fork يمكنها تشغيل CI العام دون صلاحيات كتابة؛ المسار المحلي التاريخي يسمح بمصدر same-repo مع مؤلف معتمد أو مؤلف تؤكد GitHub أن له write/maintain/admin، دون تخصيص مزود AI.

## دليل الاختبارات التاريخية

الأرشيف الأصلي V8.0 ودفتر يونيو الخاص ومصادر G2I/J/K ليست مرفوعة ولا ترفعها كـartifact/secret للمستودع العام. CI العام يصرح باستثناء V8 بالاسم وسبب الغياب المحددين فقط، ويبقي BLOCKED_NO_V80 ظاهرًا ولا يحسبه PASS. أخطاء أخرى أو SKIP مجهولة تفشل البوابة. نجاح public-core لا يشهد بنجاح الترحيل التاريخي أو التشغيل الإنتاجي.

`qa_fallback.py` بقي المسار المكمل المبني على PR6: من main موثوق كامل التاريخ ونظيف، Docker/Python3.13/Git/gh والأرشيف الأصلي الخاص: `python3.13 scripts/qa_fallback.py --pr N --v80-archive /absolute/path/original.zip --publish`. هنا الترحيل مطلوب فعلًا؛ BLOCKED لا يسمح بالنجاح. النقل لا ينفذ الكود المالي على المضيف. لا تشغل نسخة launcher غير مراجعة من PR على الماك.

Mac Local QA محفوظ ومتوقف بطلب المالك، ولم يُعد جدوله تلقائيًا. يمكن تشغيله لاحقًا بإذن المالك. لا يجوز تزوير check GitHub Actions بواسطة حالة Mac؛ تعطل GitHub/Actions قد يؤجل الدمج، وأي استعادة إدارية للحماية قرار صريح للمالك. تعطل ChatGPT/Codex/Claude لا يمنع مساعدًا آخر مصرحًا من قراءة المصدر والنتائج ومتابعة العمل.

## الإعدادات والتحقق

يُفعّل Ruleset main بعد وجود فحوص فعلية ناجحة: PR مطلوب، لا force-push/delete، latest ramses-core-ci وramses-security من GitHub Actions15368، strict up-to-date، صفر مراجعات إلزامية، ولا bypass actors. التطبيق النهائي والـIDs وروابط PRs والنتائج في تقرير تسليم المرحلة؛ هذا النص لا يدعي أن النشر أو الاختبارات اكتملت بمجرد وجود workflow.

Issue7 يبقى دفتر الدليل التشغيلي: CI يعمل على Ubuntu مستقل عن الماك، والمسار التاريخي يختبر محليًا مع الأرشيف. لا تدّعِ تشغيل الأرشيف على جهاز ثانٍ إن لم يحدث؛ لا ينشر المصدر التاريخي الخاص لاستكمال خانة اختبار. لا بيانات حقيقية أو حركة مالية أو نشر إنتاج.
