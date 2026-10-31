from pathlib import Path
root=Path(__file__).resolve().parents[1]
app=root/'app.py';s=app.read_text()

def replace_once(before,after):
 global s
 if s.count(before)!=1: raise RuntimeError(f'Expected one match, found {s.count(before)}: {before[:90]}')
 s=s.replace(before,after)

replace_once('import ledger\nimport shift_schedule','import ledger\nimport financial_integrity\nimport shift_schedule')
replace_once("            if a['code'] in ('2350','1190','2190'):\n                fail('حساب عهدة أو فرق نقدية محمي؛ استخدم دورة التسوية الموثقة وليس قيدًا يدويًا',409)",
"            if a['code'] in financial_integrity.PROTECTED_CODES:\n                fail('حساب رقابي أو إيراد طبي محمي؛ استخدم مستند التشغيل أو دورة التسوية المعتمدة',409)")
replace_once("        if j['created_by']==user['id']:fail('لا يمكن اعتماد القيد من مُدخله',403)\n        month_open(c,j['entry_date'][:7])",
"""        if j['created_by']==user['id']:fail('لا يمكن اعتماد القيد من مُدخله',403)
        if body.decision=='approve':
            rows=c.execute('SELECT account_id FROM gl_lines WHERE journal_id=?',(journal_id,)).fetchall()
            if j['origin']=='manual':
                if financial_integrity.journal_source(c,journal_id):
                    fail('هذا قيد تلقائي مرتبط بمستند؛ لا يعتمد عبر مراجعة القيود اليدوية',409)
                if financial_integrity.forbidden_manual_lines(c,[(x['account_id'],) for x in rows]):
                    fail('يحتوي القيد على حساب رقابي محمي؛ لا يمكن اعتماده يدويًا',409)
            else:
                error=financial_integrity.reversal_guard(c,j['reversal_of_id'])
                if error:fail(error,409)
        month_open(c,j['entry_date'][:7])""")
start=s.index("        if not original or original['origin'] not in ('manual','manual_reversal') or original['status']!='posted':")
end=s.index("        if entry_date<original['entry_date']:",start)
s=s[:start]+"""        error=financial_integrity.reversal_guard(c,journal_id)
        if error:fail(error,409)
"""+s[end:]
replace_once("def check_period_close_ready(c,period,user):\n    \"\"\"Single authoritative month-close gate shared by preview and posting.\"\"\"",
"""def check_period_close_ready(c,period,user):
    \"\"\"Single authoritative month-close gate shared by preview and posting.\"\"\"
    # A financial month must actually be finished in Cairo before signoff.
    if period>=current_month():
        fail('لا يمكن إقفال الشهر الجاري أو أي شهر مستقبلي قبل انتهائه بتوقيت القاهرة',409)""")
needle='''        fail("هناك فواتير مرضى لم تُرحّل إلى دفتر الأستاذ",409)

@app.get('/api/periods/preflight')'''
replacement='''        fail("هناك فواتير مرضى لم تُرحّل إلى دفتر الأستاذ",409)
    reconciliation=financial_integrity.patient_reconciliation(c,period)
    if not reconciliation['matched']:
        first=next((r for r in reconciliation['checks'] if not r['matched']),None)
        label=first['name'] if first else 'تخصيصات المرضى'
        difference=first['difference_piasters'] if first else 0
        fail(f'فشل تطابق الأستاذ مع دفتر {label}؛ الفرق {difference} قرش. افتح تقرير مطابقة حسابات المرضى.',409)
    # Historical auto-posted entries can have legacy origin=manual; only an
    # actual linked source document authorizes posting into protected accounts.
    posted=c.execute("SELECT id,origin FROM gl_journals WHERE status='posted' AND origin IN ('manual','manual_reversal') AND substr(entry_date,1,7)<=?",(period,)).fetchall()
    for j in posted:
        account_ids=[(r['account_id'],) for r in c.execute('SELECT account_id FROM gl_lines WHERE journal_id=?',(j['id'],))]
        if financial_integrity.forbidden_manual_lines(c,account_ids) and not financial_integrity.journal_source(c,j['id']):
            fail(f'القيد #{j["id"]} يؤثر على حساب رقابي دون مستند تشغيلي مرتبط؛ راجع أصل القيد قبل الإقفال',409)

@app.get('/api/accounting/patient-reconciliation')
def patient_reconciliation(period:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','viewer')
    return financial_integrity.patient_reconciliation(c,valid_month(period or current_month()))

@app.get('/api/periods/preflight')'''
replace_once(needle,replacement)
replace_once('"name":"Ramses Accounts V8.1E G0 Stabilization - Test Only"','"name":"Ramses Accounts V8.1E G2I Finance Integrity - Test Only"')
app.write_text(s)

billing=root/'billing.py';b=billing.read_text()
assert b.count('date.today().isoformat()')==2
billing.write_text(b.replace('date.today().isoformat()','cairo_today()'))

ui=root/'static'/'index.html';html=ui.read_text();html=html.replace('V8.1E-G2D','V8.1E-G2I').replace('تجربة آمنة — ليست بيانات حية','بيئة اختبار — غير معتمدة للأموال الحقيقية')
html=html.replace('صلاحيات محمية</strong><small>الحركات المعتمدة لا تُعدّل أو تُحذف', 'نسخة تجريبية</strong><small>تحتاج اعتماد رقابي قبل تسجيل أموال فعلية')
html=html.replace('    <div class="sidebar-bottom">','    <button type="button" class="nav-link sidebar-signout" id="mobileLogoutButton" aria-label="تسجيل الخروج من الحساب"><svg class="i"><use href="#i-logout"/></svg> تسجيل الخروج</button>\n    <div class="sidebar-bottom">')
ui.write_text(html)
js=root/'static'/'app.js';j=js.read_text().replace('V8.1E-G2D','V8.1E-G2I')
# Hook signout to existing host event handler rather than duplicate POST logic.
needle='$("#logoutButton")?.addEventListener'
if needle in j:
    print('Logout binding:',j[j.index(needle):j.index(needle)+250])
js.write_text(j)
print('Applied finance and UI integrity patch.')
