"""V8.0 double-entry accounting core.

Journaled cashbook movements and payroll are **provisional accounting sources**.
Do not label derived results as certified profit until opening balances,
receivables, accrued bills, inventory consumption and depreciation are reconciled.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

ACCOUNTS = (
    ('1100','مخزون الأدوية والمستلزمات','asset'),
    ('1110','أجهزة ومعدات','asset'),
    ('1120','سلف العاملين','asset'),
    ('1190','عجز خزنة تحت التسوية','asset'),
    ('1200','ذمم المرضى والجهات المدينة','asset'),
    ('2100','قروض والتزامات تمويلية','liability'),
    ('2110','رواتب مستحقة الدفع','liability'),
    ('2190','زيادة خزنة تحت التسوية','liability'),
    ('2200','دائنون وموردون','liability'),
    ('2310','Patient refund liabilities','liability'),
    ('2300','مقدمات مرضى غير مكتسبة','liability'),
    ('2350','نقدية عهدة مستلمة غير مخصصة لمرضى','liability'),
    ('3100','رأس مال وتمويل الملاك','equity'),
    ('3190','مسحوبات الملاك','equity'),
    ('4100','إيرادات الخدمات الطبية','revenue'),
    ('4195','Sales returns and allowances (contra revenue)','revenue'),
    ('4190','إيرادات تشغيل أخرى محصلة','revenue'),
    ('5100','تكلفة مستلزمات طبية مستهلكة','expense'),
    ('5110','أتعاب أطباء وفنيين مدفوعة','expense'),
    ('5120','تكاليف معامل خارجية مدفوعة','expense'),
    ('5130','إيجارات مدفوعة','expense'),
    ('5140','مرافق مدفوعة','expense'),
    ('5150','صيانة مدفوعة','expense'),
    ('5160','تسويق مدفوع','expense'),
    ('5170','مصروفات ضيافة وإدارة مدفوعة','expense'),
    ('5176','POS acquiring fees','expense'),
    ('5180','رواتب مستحقة عن الفترة','expense'),
)

# Explicit seed-category mapping. Unknown categories must NOT silently hit revenue/expense.
CATEGORY_TO_ACCOUNT = {
 'medical_revenue':'4100','other_revenue':'4190','owner_funding':'3100',
 'loan_proceeds':'2100','expense_medical':'5100','inventory_buy':'1100',
 'doctor_fees':'5110','lab_external':'5120','rent':'5130','utilities':'5140',
 'maintenance':'5150','marketing':'5160','hospitality':'5170','equipment':'1110',
 'debt_installment':'2100','owner_draw':'3190','salary_payment':'2110',
 'salary_advance':'1120','billing_invoice_receipt':'1200','billing_advance_receipt':'2300','billing_credit_refund':'2310',
 'billing_advance_refund':'2300','cash_shortage':'1190','cash_shortage_recovery':'1190','cash_overage':'2190','cash_overage_return':'2190',
 'late_cash_unallocated':'2350','pos_processing_fee':'5176',
}


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def seed_chart(c):
    """Add accounts only; never change an accountant-approved name or mapping."""
    for code,name,category in ACCOUNTS:
        c.execute('INSERT OR IGNORE INTO gl_accounts(code,name,class) VALUES (?,?,?)',(code,name,category))
    for fund in c.execute('SELECT id,name FROM funds').fetchall():
        ensure_fund_account(c, fund['id'])


def ensure_fund_account(c,fund_id):
    row=c.execute('SELECT account_id FROM gl_fund_accounts WHERE fund_id=?',(fund_id,)).fetchone()
    if row: return row[0]
    fund=c.execute('SELECT id,name FROM funds WHERE id=?',(fund_id,)).fetchone()
    if not fund:raise ValueError('Unknown cashbook fund')
    code=f'F{fund_id:05d}'
    c.execute('INSERT OR IGNORE INTO gl_accounts(code,name,class,control) VALUES (?,?,?,?)',
              (code,'حساب رقابي: '+fund['name'],'asset','fund'))
    account=c.execute('SELECT id FROM gl_accounts WHERE code=? AND control=?',(code,'fund')).fetchone()
    if not account:raise ValueError('GL control account code conflict')
    c.execute('INSERT INTO gl_fund_accounts(fund_id,account_id) VALUES (?,?)',(fund_id,account[0]))
    return account[0]


def account_by_code(c,code):
    row=c.execute('SELECT id FROM gl_accounts WHERE code=? AND active=1',(code,)).fetchone()
    if not row: raise ValueError('Missing active accounting account '+code)
    return row[0]


def _journal(c,*,entry_date,memo,origin,source_id,created_by,reviewed_by=None,lines,reversal_of=None):
    """Create pending journal and post only after DB verifies balance (caller owns transaction)."""
    if source_id is not None:
        existing=c.execute('SELECT id FROM gl_journals WHERE origin=? AND source_id=?',(origin,source_id)).fetchone()
        if existing:return existing[0]
    if len(lines)<2 or sum(x[1] for x in lines)!=sum(x[2] for x in lines) or sum(x[1] for x in lines)<=0:
        raise ValueError('GL journal not balanced')
    cur=c.execute('''INSERT INTO gl_journals(entry_date,memo,origin,source_id,reversal_of_id,status,
               created_by,created_at) VALUES (?,?,?,?,?,'pending',?,?)''',
              (entry_date,memo,origin,source_id,reversal_of,created_by,stamp()))
    for account_id,debit,credit,department in lines:
        if (debit>0)==(credit>0) or min(debit,credit)<0:
            raise ValueError('Invalid debit/credit line')
        c.execute('''INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters,department_id)
                     VALUES (?,?,?,?,?)''',(cur.lastrowid,account_id,debit,credit,department))
    if reviewed_by is not None:
        c.execute('''UPDATE gl_journals SET status='posted',reviewed_by=?,reviewed_at=? WHERE id=?''',
                  (reviewed_by,stamp(),cur.lastrowid))
    return cur.lastrowid


def post_voucher(c,v,reviewer_id):
    """Mirror one approved cashbook voucher as an immutable, balanced GL entry."""
    amount=int(v['amount_piasters'])
    if v['kind']=='transfer':
        lines=[(ensure_fund_account(c,v['to_fund_id']),amount,0,None),
               (ensure_fund_account(c,v['from_fund_id']),0,amount,None)]
    else:
        cat=c.execute('SELECT code FROM categories WHERE id=?',(v['category_id'],)).fetchone()
        if not cat or cat['code'] not in CATEGORY_TO_ACCOUNT:
            raise ValueError('Unknown GL category. Accounting mapping required before approval.')
        other=account_by_code(c,CATEGORY_TO_ACCOUNT[cat['code']])
        cash=ensure_fund_account(c,v['from_fund_id'])
        dept=v['department_id']
        if v['kind']=='receipt':
            lines=[(cash,amount,0,dept),(other,0,amount,dept)]
        elif v['kind']=='payment':
            lines=[(other,amount,0,dept),(cash,0,amount,dept)]
        else:raise ValueError('Unsupported voucher kind')
    if v['reversal_of_id'] is not None:
        lines=[(account,credit,debit,dept) for account,debit,credit,dept in lines]
    return _journal(c,entry_date=v['date'],memo='سند '+v['voucher_no'],origin='voucher',
                    source_id=v['id'],created_by=v['created_by'],reviewed_by=reviewer_id,lines=lines)


def post_payroll(c,accr,reviewer_id):
    amount=int(accr['net_piasters'])
    if amount<=0:return None  # Zero-pay approvals have no monetary journal; track separately.
    return _journal(c,entry_date=accr['period']+'-01',memo='استحقاق راتب موظف '+str(accr['employee_id']),
                    origin='payroll',source_id=accr['id'],created_by=accr['approved_by'],reviewed_by=reviewer_id,
                    lines=[(account_by_code(c,'5180'),amount,0,None),
                           (account_by_code(c,'2110'),0,amount,None)])


def post_allocation(c,allocation_id,employee_id,period,amount,actor_id):
    return _journal(c,entry_date=period+'-01',memo='تسوية سلفة موظف '+str(employee_id),
                    origin='allocation',source_id=allocation_id,created_by=actor_id,reviewed_by=actor_id,
                    lines=[(account_by_code(c,'2110'),amount,0,None),
                           (account_by_code(c,'1120'),0,amount,None)])


def trial_balance(c,period):
    rows=[dict(r) for r in c.execute('''SELECT a.id,a.code,a.name,a.class,a.control,
      COALESCE(SUM(CASE WHEN j.status='posted' AND substr(j.entry_date,1,7)<=? THEN l.debit_piasters ELSE 0 END),0) debit_total,
      COALESCE(SUM(CASE WHEN j.status='posted' AND substr(j.entry_date,1,7)<=? THEN l.credit_piasters ELSE 0 END),0) credit_total
      FROM gl_accounts a LEFT JOIN gl_lines l ON l.account_id=a.id
      LEFT JOIN gl_journals j ON j.id=l.journal_id GROUP BY a.id ORDER BY a.code''',(period,period))]
    for r in rows:
        delta=r['debit_total']-r['credit_total']
        r['closing_debit_piasters']=max(0,delta)
        r['closing_credit_piasters']=max(0,-delta)
    debits=sum(r['closing_debit_piasters'] for r in rows)
    credits=sum(r['closing_credit_piasters'] for r in rows)
    return {'period':period,'accounts':rows,'debit_piasters':debits,'credit_piasters':credits,
            'balanced':debits==credits,'description':'ميزان دفتر الأستاذ للأجزاء المرحلة فقط - غير معتمد كقوائم مالية كاملة'}


def coverage(c,period):
    values={}
    values['unposted_vouchers']=c.execute('''SELECT count(*) FROM vouchers v
      WHERE substr(v.date,1,7)<=? AND v.status IN ('approved','reversed') AND NOT EXISTS
      (SELECT 1 FROM gl_journals j WHERE j.origin='voucher' AND j.source_id=v.id AND j.status='posted')''',(period,)).fetchone()[0]
    values['unposted_payroll']=c.execute('''SELECT count(*) FROM payroll_accruals p
      WHERE p.period<=? AND p.net_piasters>0 AND p.signoff_status IN ('approved','legacy') AND NOT EXISTS
      (SELECT 1 FROM gl_journals j WHERE j.origin='payroll' AND j.source_id=p.id AND j.status='posted')''',(period,)).fetchone()[0]
    values['unposted_allocations']=c.execute('''SELECT count(*) FROM advance_allocations a
      WHERE a.period<=? AND NOT EXISTS
      (SELECT 1 FROM gl_journals j WHERE j.origin='allocation' AND j.source_id=a.id AND j.status='posted')''',(period,)).fetchone()[0]
    from opening_balances import outstanding
    values['unverified_opening_funds']=len(outstanding(c,period))
    values['pending_journals']=c.execute("SELECT count(*) FROM gl_journals WHERE status='pending' AND substr(entry_date,1,7)<=?",(period,)).fetchone()[0]
    values['historical_unverified']=c.execute("SELECT count(*) FROM legacy_entries WHERE import_status='archive_unverified'").fetchone()[0]
    values['issued_billing_invoices']=c.execute('SELECT COUNT(*) FROM billing_invoices WHERE substr(issued_date,1,7)<=?',(period,)).fetchone()[0]
    values['unposted_billing_invoices']=c.execute('SELECT COUNT(*) FROM billing_invoices i LEFT JOIN gl_journals j ON j.id=i.journal_id WHERE substr(i.issued_date,1,7)<=? AND (j.id IS NULL OR j.status!="posted")',(period,)).fetchone()[0]
    values['unissued_drafts']=c.execute('''SELECT COUNT(*) FROM billing_invoice_drafts d
      WHERE NOT EXISTS (SELECT 1 FROM billing_invoices i WHERE i.draft_id=d.id)
      AND EXISTS (SELECT 1 FROM billing_invoice_draft_lines dl
        JOIN billing_case_lines l ON l.id=dl.case_line_id
        JOIN billing_cases b ON b.id=l.case_id
        LEFT JOIN bed_night_charges n ON n.case_line_id=l.id
        WHERE dl.draft_id=d.id
          AND substr(COALESCE(n.night_date,l.service_date,b.business_date),1,7)<=?)''',
          (period,)).fetchone()[0]
    values['approved_patient_credits']=c.execute("SELECT COUNT(*) FROM billing_credit_requests WHERE status='approved' AND substr(decided_at,1,7)<=?",(period,)).fetchone()[0]
    values['pending_patient_refunds']=c.execute("SELECT COUNT(*) FROM billing_refund_requests WHERE status IN ('pending','approved')").fetchone()[0]
    values['not_final']=True
    values['readiness_reason']='نقص الأرصدة الافتتاحية المدققة وسياسات الخصومات والإشعارات الدائنة والمخزون والإهلاك؛ لا تستخدم الناتج كصافي ربح.'
    return values
