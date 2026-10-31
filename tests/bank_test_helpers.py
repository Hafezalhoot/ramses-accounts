"""Test-only complete bank statement from already-posted synthetic movements."""
import csv
import io
from decimal import Decimal
from bootstrap import connect
from app import bank_ledger_at


def signoff_bank_month(owner, oh, reviewer, rh, bank_id, month):
    with connect() as c:
        opening,closing=bank_ledger_at(c,bank_id,month)
        rows=c.execute('''SELECT m.id,m.booked_on,m.amount_piasters,v.voucher_no
                          FROM fund_movements m JOIN vouchers v ON v.id=m.voucher_id
                          WHERE m.fund_id=? AND substr(m.booked_on,1,7)=? ORDER BY m.id''',
                       (bank_id,month)).fetchall()
    assert rows, 'Expected test bank movements'
    # G2N: explicit owner-issued bank grant is needed even for a reviewer.
    # The test must model authorization rather than bypass it by role.
    user_id=reviewer.get('/api/me').json()['id']
    grant=owner.post('/api/fund-access',headers=oh,json={
        'user_id':user_id,'fund_id':bank_id,'can_submit':True,
        'reason':'Grant scoped bank statement import solely for synthetic QA'})
    assert grant.status_code==200,(grant.status_code,grant.text)
    output=io.StringIO()
    w=csv.writer(output)
    w.writerow(['date','description','amount','reference'])
    for r in rows:
        w.writerow([r['booked_on'],'حركة دفتر '+r['voucher_no'],
                    str(Decimal(r['amount_piasters'])/100),r['voucher_no']])
    r=reviewer.post('/api/bank-reconciliation/import',headers=rh,
              data={'fund_id':bank_id,'period':month,'opening_balance':str(Decimal(opening)/100),
                    'closing_balance':str(Decimal(closing)/100)},
              files={'file':('synthetic_test_only.csv',io.BytesIO(output.getvalue().encode('utf-8-sig')),'text/csv')})
    assert r.status_code==200,(r.status_code,r.text)
    batch_id=r.json()['batch_id']
    report=owner.get(f'/api/bank-reconciliation?period={month}&fund_id={bank_id}').json()
    by_ref={x['voucher_no']:x for x in report['unmatched_ledger']}
    for line in report['lines']:
        movement=by_ref[line['reference']]
        r=owner.post(f'/api/bank-reconciliation/{batch_id}/match',headers=oh,
                     json={'line_id':line['id'],'movement_id':movement['movement_id']})
        assert r.status_code==200,(r.status_code,r.text)
    r=owner.post(f'/api/bank-reconciliation/{batch_id}/approve',headers=oh,
                 json={'note':'اعتماد كشف بنك وهمي لاختبار الإقفال الشهري'})
    assert r.status_code==200,(r.status_code,r.text)
