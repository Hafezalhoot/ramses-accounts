# استكمال رمسيس بأي مساعد — البداية الحالية

اقرأ AGENTS.md ثم PUBLIC_CI_AI_WORKFLOW_AR.md. السياسة الحالية بعد موافقة المالك6 نوفمبر2026: Public وGitHub Actions بصلاحيات محدودة، ثم Rulesets بعد نجاح CI الفعلي. تعليمات no-Actions القديمة محفوظة في تاريخ Git.

1. راجع main وPRs الحالية وSHA الحقيقي. اعمل على فرع مستقل.
2. افتح PR وانتظر `ramses-core-ci` و`ramses-security` على رأسه الحالي. راجع الفرق والأعداد؛ BLOCKED التاريخي وSKIP ليست PASS.
3. حدّث الفرع إذا تقدم main وأعد الفحص. من main موثوق ونظيف شغّل `python3.13 scripts/qa_checked_merge.py --pr N`، ثم `--merge` عند وجود تفويض الدمج ونجاح الشروط. لا حاجة لموافقة موديل معين، ولا bypass أو force-push.
4. للأرشيف التاريخي الأصلي استعمل qa_fallback.py مع --v80-archive؛ لا ترفع الأرشيف أو logs أو DB إلى GitHub. Mac Local QA احتياطي وجدوله متوقف حاليًا.

التفاصيل والحدود في AI_FAILOVER_AND_MERGE_AR.md. النشر العام لا ينشر تطبيق المستشفى ولا يعتمد التشغيل الإنتاجي.
