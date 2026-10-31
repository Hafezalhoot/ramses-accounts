"""Independent, document-linked openings for cash/bank/wallet GL controls.

No blind assertion about historic money: the staff must verify the external
statement or signed physical count, then an authorized different user posts a
balanced source-linked GL journal. This is NOT a full opening trial balance.
"""
from __future__ import annotations

from datetime import date


def detail(c, period):
    rows=[]
    for f in c.execute('''SELECT f.id,f.code,f.name,f.kind,f.active,f.opening_piasters,
                     r.id review_id,r.amount_piasters review_amount_piasters,r.status review_status,r.effective_date,r.evidence_kind,
                     r.evidence_reference,r.evidence_note,r.offset_account_id,
                     r.created_by,r.reviewed_by,r.journal_id
             FROM funds f LEFT JOIN fund_opening_reviews r ON r.fund_id=f.id
                AND r.status IN ('pending','approved') ORDER BY f.id'''):
        r=dict(f)
        amount=int(r['opening_piasters'])
        approved=r['review_status']=='approved'
        is_due=amount>0
        valid=approved
        reason=''
        if not approved:
            reason='لا يوجد محضر افتتاحي معتمد' if is_due else 'صفر بدون مستند افتتاحي (إثباته اختياري للتجربة)'
        elif amount != r['review_amount_piasters']:
            valid=False;reason='قيمة الافتتاح الحالي لا تطابق المحضر'
        if approved and r['effective_date'][:7] > period:
            valid=False;reason='قيد الافتتاح بتاريخ لاحق للفترة'
        if approved and amount>0 and valid:
            j=c.execute('''SELECT id,status,origin,source_id,entry_date,created_by,reviewed_by
                     FROM gl_journals WHERE id=?''',(r['journal_id'],)).fetchone()
            lines=c.execute('''SELECT l.account_id,l.debit_piasters,l.credit_piasters
                  FROM gl_lines l WHERE l.journal_id=?''',(r['journal_id'],)).fetchall()
            fa=c.execute('SELECT account_id FROM gl_fund_accounts WHERE fund_id=?',(r['id'],)).fetchone()
            if (not j or j['status']!='posted' or j['origin']!='manual'
                or j['source_id']!=r['review_id'] or j['entry_date']!=r['effective_date']
                or j['reviewed_by']!=r['reviewed_by'] or j['created_by']!=r['created_by']
                or not fa or len(lines)!=2 or not any(
                    x['account_id']==fa['account_id'] and x['debit_piasters']==amount
                    and x['credit_piasters']==0 for x in lines)
                or not any(x['account_id']==r['offset_account_id'] and x['credit_piasters']==amount
                    and x['debit_piasters']==0 for x in lines)):
                valid=False;reason='القيد الافتتاحي غير مرحل أو لا يطابق المستند المعتمد'
        r['verified_as_of_period']=bool(valid)
        r['review_needed']=bool(is_due and not valid)
        r['review_issue']=reason
        rows.append(r)
    return rows


def outstanding(c,period):
    return [r for r in detail(c,period) if r['review_needed']]
