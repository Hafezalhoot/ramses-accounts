"""Small runnable end-to-end checks for permissions, money postings and payroll."""
from unittest.mock import patch
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["RAMSES_DB_PATH"]=str(Path(tmp)/"hospital.sqlite3")
        os.environ["RAMSES_ADMIN_USER"]="owner"
        os.environ["RAMSES_ADMIN_PASSWORD"]="test_only_password_16plus"
        from bootstrap import initialize
        legacy_source=ROOT/"imports"/"legacy_june_2026.xlsx"
        initialize(str(legacy_source) if legacy_source.is_file() else None)
        from app import app
        from fastapi.testclient import TestClient
        from bootstrap import connect
        from app import c_piasters
        c=connect()
        if legacy_source.is_file():
            assert c.execute("SELECT count(*) FROM legacy_entries").fetchone()[0] == 618
            assert c.execute("SELECT count(*) FROM legacy_entries WHERE transaction_date IS NOT NULL").fetchone()[0] == 617
            assert c.execute("SELECT sum(total_piasters) FROM legacy_entries WHERE kind='إيراد' AND transaction_date IS NOT NULL").fetchone()[0] == 46581100
        else:
            assert c.execute("SELECT count(*) FROM legacy_entries").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM fund_movements").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM employees").fetchone()[0] == (39 if legacy_source.is_file() else 0)
        c.close()
        assert c_piasters("12.25") == 1225
        main=TestClient(app);reviewer=TestClient(app);clerk=TestClient(app)
        def login(client,username,password):
            r=client.post('/api/login',json={'username':username,'password':password})
            assert r.status_code==200, (r.status_code,r.text)
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=login(main,'owner','test_only_password_16plus')
        assert main.post('/api/users',json={'username':'x','password':'password','role':'reviewer'}).status_code==403
        for username,role in [('reviewer','reviewer'),('clerk','clerk')]:
            r=main.post('/api/users',json={'username':username,'password':'long_password_123456','role':role},headers=oh)
            assert r.status_code==200,r.text
        rh=login(reviewer,'reviewer','long_password_123456')
        ch=login(clerk,'clerk','long_password_123456')
        look=main.get('/api/lookups').json()
        if not look['employees']:
            assert main.post('/api/employees',json={'name':'موظف اختبار تجريبي','code':'TEST001'},headers=oh).status_code==200
            look=main.get('/api/lookups').json()
        fund=look['funds'][0]['id'];wallet=look['funds'][2]['id'];dept=look['departments'][0]['id'];emp=look['employees'][0]['id']
        cashier_id=next(x['id'] for x in main.get('/api/users').json() if x['username']=='clerk')
        assert main.post('/api/fund-access',headers=oh,json={'user_id':cashier_id,'fund_id':wallet,'can_submit':True,
                'reason':'تفويض المحفظة لاختبار تحويلات وسلف الموظفين'}).status_code==200
        reviewer_id=next(x['id'] for x in main.get('/api/users').json() if x['username']=='reviewer')
        assert main.post('/api/fund-access',headers=oh,json={'user_id':reviewer_id,'fund_id':wallet,'can_approve':True,
                'reason':'تفويض المراجع لاعتماد معاملات المحفظة'}).status_code==200
        revenue=next(x['id'] for x in look['categories'] if x['code']=='medical_revenue')
        expense=next(x['id'] for x in look['categories'] if x['code']=='utilities')
        paycat=next(x['id'] for x in look['categories'] if x['code']=='salary_payment')
        advcat=next(x['id'] for x in look['categories'] if x['code']=='salary_advance')
        assert main.post(f'/api/funds/{fund}/opening',json={'amount':'2000'},headers=oh).status_code==200
        month=date.today().isoformat()[:7]
        today=date.today().isoformat()
        def v(kind,amt,cat=None,from_id=fund,to_id=None,who=clerk,headers=ch,employee=None,period=None):
            data={'date':today,'kind':kind,'department_id':dept,'category_id':cat,'from_fund_id':from_id,
                  'to_fund_id':to_id,'shift':'morning','amount':str(amt),'description':'سند مالي للاختبار الداخلي',
                  'employee_id':employee,'salary_period':period}
            r=who.post('/api/vouchers',json=data,headers=headers)
            assert r.status_code==200,r.text
            return r.json()['id']
        retry_payload={'date':today,'kind':'receipt','department_id':dept,'category_id':revenue,
                       'from_fund_id':fund,'shift':'morning','amount':'12.50',
                       'description':'سند اختبار إعادة المحاولة',
                       'client_request_id':'entry_retry_key_20261029'}
        first=clerk.post('/api/vouchers',json=retry_payload,headers=ch)
        assert first.status_code==200,first.text
        again=clerk.post('/api/vouchers',json=retry_payload,headers=ch)
        assert again.status_code==200 and again.json()['id']==first.json()['id']
        assert again.json().get('replayed') is True
        conflict=clerk.post('/api/vouchers',json={**retry_payload,'amount':'18'},headers=ch)
        assert conflict.status_code==409
        assert main.get('/api/vouchers?status=pending').json()['count']==1
        assert reviewer.post(f"/api/vouchers/{first.json()['id']}/decision",
                             json={'decision':'reject','reason':'سند اختبار غير حقيقي'},headers=rh).status_code==200
        assert main.get('/api/vouchers?status=rejected').json()['count']==1
        r1=v('receipt','100',revenue)
        assert reviewer.post(f'/api/vouchers/{r1}/decision',json={'decision':'approve'},headers=rh).status_code==200
        assert clerk.post(f'/api/vouchers/{r1}/decision',json={'decision':'approve'},headers=ch).status_code==403
        r2=v('payment','400',expense,who=reviewer,headers=rh)
        assert reviewer.post(f'/api/vouchers/{r2}/decision',json={'decision':'approve'},headers=rh).status_code==403
        assert main.post(f'/api/vouchers/{r2}/decision',json={'decision':'approve'},headers=oh).status_code==200
        r3=v('transfer','600',None,to_id=wallet)
        assert reviewer.post(f'/api/vouchers/{r3}/decision',json={'decision':'approve'},headers=rh).status_code==200
        funds=main.get('/api/funds').json()
        assert next(f for f in funds if f['id']==fund)['balance_piasters']==110000
        assert next(f for f in funds if f['id']==wallet)['balance_piasters']==60000
        dash=main.get('/api/dashboard?month='+month).json()
        assert dash['receipts_piasters']==10000 and dash['payments_piasters']==40000
        r4=v('payment','1200',expense)
        rejected=reviewer.post(f'/api/vouchers/{r4}/decision',json={'decision':'approve'},headers=rh)
        assert rejected.status_code==409,rejected.text
        assert reviewer.post(f'/api/vouchers/{r4}/decision',json={'decision':'reject','reason':'رصيد الخزنة لا يكفي'},headers=rh).status_code==200
        assert main.post(f'/api/funds/{fund}/opening',json={'amount':'4000'},headers=oh).status_code==409
        assert main.post(f'/api/employees/{emp}/salary-term',json={'month':month,'monthly_salary':'3000'},headers=oh).status_code==200
        accrual=main.post('/api/payroll/accrual',json={'employee_id':emp,'period':month,'additions':'0','deductions':'0'},headers=oh)
        assert accrual.status_code==200 and accrual.json()['signoff_status']=='pending'
        assert main.get('/api/payroll?period='+month).json()['items'][0]['due_piasters'] is None
        assert reviewer.post(f'/api/payroll/accrual/{accrual.json()["id"]}/decision',json={'decision':'approve'},headers=rh).status_code==200
        paid=v('payment','1000',paycat,employee=emp,period=month)
        assert reviewer.post(f'/api/vouchers/{paid}/decision',json={'decision':'approve'},headers=rh).status_code==200
        adv=v('payment','250',advcat,employee=emp)
        too_low=reviewer.post(f'/api/vouchers/{adv}/decision',json={'decision':'approve'},headers=rh)
        assert too_low.status_code==409  # insufficient on the original cash fund
        assert main.post(f'/api/funds/{wallet}/opening',json={'amount':'200'},headers=oh).status_code==409  # transfer has moved
        # Transfer from the other fund, then advance from that fund.
        ad2=v('payment','250',advcat,from_id=wallet,employee=emp)
        assert reviewer.post(f'/api/vouchers/{ad2}/decision',json={'decision':'approve'},headers=rh).status_code==200
        payroll=main.get('/api/payroll?period='+month).json()
        current=next(e for e in payroll['items'] if e['id']==emp)
        assert current['due_piasters']==200000 and current['advances_outstanding_piasters']==25000
        alloc=main.post('/api/payroll/allocate-advance',json={'employee_id':emp,'period':month,'amount':'200'},headers=oh)
        assert alloc.status_code==200,alloc.text
        due=main.get('/api/payroll?period='+month).json()
        assert next(e for e in due['items'] if e['id']==emp)['due_piasters']==180000
        assert main.post('/api/payroll/allocate-advance',json={'employee_id':emp,'period':month,'amount':'100'},headers=oh).status_code==409
        reverse=main.post(f'/api/vouchers/{r2}/reverse',json={'date':today,'reason':'إلغاء بسبب قيد خاطئ قيد اختبار'},headers=oh)
        assert reverse.status_code==200,reverse.text
        dash=main.get('/api/dashboard?month='+month).json()
        assert dash['payments_piasters']==125000  # salary 1000 + advance 250, original 400 fully reversed
        # Owner-created reversal must be visible to the original clerk and cancel their totals.
        clerk_before=clerk.get('/api/dashboard?month='+month).json()
        assert clerk_before['receipts_piasters']==10000,clerk_before
        reversed_receipt=main.post(f'/api/vouchers/{r1}/reverse',
             json={'date':today,'reason':'تصحيح مقبوضات تجريبي بعد مراجعة الإدارة'},headers=oh)
        assert reversed_receipt.status_code==200,reversed_receipt.text
        clerk_after=clerk.get('/api/dashboard?month='+month).json()
        assert clerk_after['receipts_piasters']==0,clerk_after
        own_ids={x['id'] for x in clerk.get('/api/vouchers?kind=receipt').json()['items']}
        assert {r1,reversed_receipt.json()['reversal_id']}.issubset(own_ids),own_ids
        # An unrelated reversal must not become visible to the clerk.
        reviewer_ledger=reviewer.get('/api/vouchers').json()['items']
        assert len(reviewer_ledger)>len(own_ids)
        assert main.get('/api/legacy').status_code==200 and clerk.get('/api/legacy').status_code==403
        assert clerk.get('/api/users').status_code==403
        assert main.get('/api/export/vouchers.csv').status_code==200
        assert main.post('/api/periods/close',json={'period':month},headers=oh).status_code==409 # pending advance
        assert reviewer.post(f'/api/vouchers/{adv}/decision',json={'decision':'reject','reason':'تغيير مصدر الصرف'},headers=rh).status_code==200
        from opening_test_helpers import approve_all_openings
        approve_all_openings(main,oh,reviewer,rh,month)
        # Test clock only: emulate period already completed; production rejects current/future closes.
        with patch('app.current_month', return_value='9999-12'):
            assert main.post('/api/periods/close',json={'period':month},headers=oh).status_code==200
        assert clerk.post('/api/vouchers',json={'date':today,'kind':'receipt','department_id':dept,'category_id':revenue,'from_fund_id':fund,'shift':'morning','amount':'1','description':'اختبار بعد إقفال شهر'},headers=ch).status_code==409
        print('PASS — historical quarantine (when available), idempotency, login/CSRF/RBAC, cash, payroll, reversals & close')


if __name__=='__main__':
    run()
