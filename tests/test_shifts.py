"""Staging financial acceptance: blind count -> variance -> recount -> dual approval.

No Google, external network, historical ledger, or real employee names.
"""
from unittest.mock import patch
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as temp:
        os.environ['RAMSES_DB_PATH']=str(Path(temp)/'shifts.db')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='a_long_staging_only_secret'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,clerk,reviewer=(TestClient(app) for _ in range(3))

        def sign_in(client,name,secret):
            r=client.post('/api/login',json={'username':name,'password':secret})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}

        oh=sign_in(owner,'owner','a_long_staging_only_secret')
        for who,role in [('cashier','clerk'),('controller','reviewer')]:
            response=owner.post('/api/users',json={'username':who,'password':'test_long_secret_4567','role':role},headers=oh)
            assert response.status_code==200,response.text
        ch=sign_in(clerk,'cashier','test_long_secret_4567')
        rh=sign_in(reviewer,'controller','test_long_secret_4567')
        look=owner.get('/api/lookups').json()
        cash=next(x['id'] for x in look['funds'] if x['code']=='cash_main')
        dept=look['departments'][0]['id']
        receipt=next(x['id'] for x in look['categories'] if x['code']=='medical_revenue')
        payment=next(x['id'] for x in look['categories'] if x['code']=='utilities')
        today=date.today().isoformat()
        month=today[:7]
        assert owner.post(f'/api/funds/{cash}/opening',json={'amount':'1000'},headers=oh).status_code==200

        def create(kind,amt,shift='morning'):
            payload={'date':today,'kind':kind,'from_fund_id':cash,'department_id':dept,
                     'category_id':receipt if kind=='receipt' else payment,'shift':shift,
                     'amount':str(amt),'description':'تحصيل تجريبي خاص باختبار الورديات'}
            return clerk.post('/api/vouchers',json=payload,headers=ch)

        # New shift starts before posting; opening balance becomes immutable.
        opened=clerk.post('/api/shifts/open',json={'fund_id':cash,'business_date':today,'shift':'morning'},headers=ch)
        assert opened.status_code==200,opened.text
        sid=opened.json()['id']
        assert owner.post(f'/api/funds/{cash}/opening',json={'amount':'2500'},headers=oh).status_code==409
        assert reviewer.post('/api/shifts/open',json={'fund_id':cash,'business_date':today,'shift':'evening'},headers=rh).status_code==409
        cashier_open=clerk.get(f'/api/shifts?month={month}').json()['items'][0]
        assert cashier_open['id']==sid and 'expected_piasters' not in cashier_open
        assert 'opening_piasters' not in cashier_open
        assert owner.get(f'/api/shifts?month={month}').json()['items'][0]['opening_piasters']==100000

        first=create('receipt','100')
        assert first.status_code==200,first.text
        first_id=first.json()['id']
        assert reviewer.post(f'/api/vouchers/{first_id}/decision',json={'decision':'approve'},headers=rh).status_code==200
        second=create('payment','50')
        assert second.status_code==200,second.text
        second_id=second.json()['id']
        assert reviewer.post(f'/api/vouchers/{second_id}/decision',json={'decision':'approve'},headers=rh).status_code==200
        # Reviewer can inspect source vouchers composing the shift balance.
        movement=reviewer.get(f'/api/shifts/{sid}/movements')
        assert movement.status_code==200,movement.text
        d=movement.json()
        assert len(d['movements'])==2 and d['credited_piasters']==10000 and d['debited_piasters']==5000
        assert d['expected_piasters']==105000 and d['shift']['opening_piasters']==100000
        assert clerk.get(f'/api/shifts/{sid}/movements').status_code==403
        # Pending voucher blocks count, never permits an incomplete shift close.
        pending=create('receipt','5')
        assert pending.status_code==200,pending.text
        assert clerk.post(f'/api/shifts/{sid}/count',json={'counted_amount':'1040'},headers=ch).status_code==409
        assert reviewer.post(f'/api/vouchers/{pending.json()["id"]}/decision',json={'decision':'reject','reason':'غير مسجل في وردية التجربة'},headers=rh).status_code==200
        assert reviewer.post(f'/api/shifts/{sid}/count',json={'counted_amount':'1050'},headers=rh).status_code==403

        mismatch=clerk.post(f'/api/shifts/{sid}/count',json={'counted_amount':'1040','note':'نقص عشرة جنيهات'},headers=ch)
        assert mismatch.status_code==200,mismatch.text
        assert mismatch.json()['variance_piasters']==-1000
        assert owner.post(f'/api/shifts/{sid}/review',json={'decision':'approve'},headers=oh).status_code==409
        # Once submitted, new postings cannot change the ledger while under review.
        assert create('receipt','3').status_code==409
        assert owner.post('/api/periods/close',json={'period':month},headers=oh).status_code==409
        assert clerk.post(f'/api/shifts/{sid}/review',json={'decision':'recount','reason':'إعادة حساب'},headers=ch).status_code==403
        reopen=reviewer.post(f'/api/shifts/{sid}/review',json={'decision':'recount','reason':'مراجعة فرق الجرد وإعادة العد'},headers=rh)
        assert reopen.status_code==200,reopen.text
        assert reopen.json()['status']=='open'
        actual=clerk.post(f'/api/shifts/{sid}/count',json={'counted_amount':'1050','note':'إعادة عد نقدي'},headers=ch)
        assert actual.status_code==200 and actual.json()['variance_piasters']==0,actual.text
        assert clerk.post(f'/api/shifts/{sid}/review',json={'decision':'approve'},headers=ch).status_code==403
        closed=reviewer.post(f'/api/shifts/{sid}/review',json={'decision':'approve','reason':'مطابقة الجرد'},headers=rh)
        assert closed.status_code==200 and closed.json()['status']=='closed',closed.text
        assert reviewer.post(f'/api/shifts/{sid}/review',json={'decision':'approve'},headers=rh).status_code==409
        assert create('payment','1').status_code==409
        # Reversal changes the physical drawer, so it requires an active shift.
        assert owner.post(f'/api/vouchers/{first_id}/reverse',json={
            'date':today,'reason':'تصحيح تسوية في صندوق مغلق'},headers=oh).status_code==409
        evening=clerk.post('/api/shifts/open',json={'fund_id':cash,'business_date':today,'shift':'evening'},headers=ch)
        assert evening.status_code==200,evening.text
        eid=evening.json()['id']
        assert owner.post(f'/api/vouchers/{first_id}/reverse',json={
            'date':today,'reason':'تصحيح الإيراد داخل وردية مسائية مفتوحة'},headers=oh).status_code==200
        f=owner.get('/api/funds').json()
        assert next(x for x in f if x['id']==cash)['balance_piasters']==95000
        # The original shift's signed ledger is immutable; reversal belongs to evening.
        first_ledger=reviewer.get(f'/api/shifts/{sid}/movements').json()
        evening_ledger=reviewer.get(f'/api/shifts/{eid}/movements').json()
        assert first_ledger['expected_piasters']==105000
        assert evening_ledger['debited_piasters']==10000 and evening_ledger['expected_piasters']==95000
        assert len(evening_ledger['movements'])==1 and evening_ledger['movements'][0]['voucher_no'].startswith('REV-')
        # Unresolved active shift blocks month close even without pending vouchers.
        assert owner.post('/api/periods/close',json={'period':month},headers=oh).status_code==409
        assert clerk.post(f'/api/shifts/{eid}/count',json={'counted_amount':'950'},headers=ch).status_code==200
        assert owner.post(f'/api/shifts/{eid}/review',json={'decision':'approve'},headers=oh).status_code==200
        from opening_test_helpers import approve_all_openings
        approve_all_openings(owner,oh,reviewer,rh,month)
        # Test clock only: emulate period already completed; production rejects current/future closes.
        with patch('app.current_month', return_value='9999-12'):
            assert owner.post('/api/periods/close',json={'period':month},headers=oh).status_code==200
        assert clerk.post('/api/shifts/open',json={'fund_id':cash,'business_date':today,'shift':'night'},headers=ch).status_code==409
        with connect() as c:
            assert c.execute("SELECT COUNT(*) FROM shift_sessions WHERE status='closed'").fetchone()[0]==2
            assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='request_shift_recount'").fetchone()[0]==1
        print('PASS — shift open, blind count, pending guard, variance, segregation, recount, freeze, reversal, month close')

if __name__=='__main__':run()
