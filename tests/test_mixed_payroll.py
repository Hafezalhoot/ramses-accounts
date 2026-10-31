"""V7.4 mixed monthly/hourly payroll: accurate cents, independent time approval and immutable snapshots."""
from unittest.mock import patch
import os
import sys
import tempfile
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'mixed.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='strong_test_only_owner_pw_123'
        os.environ.pop('RAMSES_REQUIRE_PAYMENT_EVIDENCE',None)
        from bootstrap import initialize,connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app,hourly_wage
        owner,reviewer,clerk,viewer=(TestClient(app) for _ in range(4))
        def login(client,who,password):
            r=client.post('/api/login',json={'username':who,'password':password})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=login(owner,'owner','strong_test_only_owner_pw_123')
        for n,role in [('reviewer','reviewer'),('clerk','clerk'),('viewer','viewer')]:
            assert owner.post('/api/users',json={'username':n,'password':'long_test_auth_pass_123','role':role},headers=oh).status_code==200
        rh=login(reviewer,'reviewer','long_test_auth_pass_123')
        ch=login(clerk,'clerk','long_test_auth_pass_123')
        vh=login(viewer,'viewer','long_test_auth_pass_123')
        def emp(name,code):
            r=owner.post('/api/employees',json={'name':name,'code':code},headers=oh)
            assert r.status_code==200,r.text
            return r.json()['id']
        hourly=emp('ممرض بنظام الساعة','HR001')
        monthly=emp('موظف شهري','MN001')
        not_set=emp('موظف بدون تعاقد','NS001')
        period='2026-10'; day='2026-10-13'
        assert owner.post('/api/employees/999/salary-term',json={'month':period,'pay_type':'hourly','hourly_rate':'75.55'},headers=oh).status_code==400
        assert reviewer.post(f'/api/employees/{hourly}/salary-term',json={'month':period,'pay_type':'hourly','hourly_rate':'75.55'},headers=rh).status_code==403
        assert owner.post(f'/api/employees/{hourly}/salary-term',json={'month':period,'pay_type':'hourly','hourly_rate':'0'},headers=oh).status_code==400
        assert owner.post(f'/api/employees/{hourly}/salary-term',json={'month':period,'pay_type':'monthly','monthly_salary':'500','hourly_rate':'75.55'},headers=oh).status_code==400
        assert owner.post(f'/api/employees/{hourly}/salary-term',json={'month':period,'pay_type':'hourly','hourly_rate':'75.55'},headers=oh).status_code==200
        assert owner.post(f'/api/employees/{monthly}/salary-term',json={'month':period,'monthly_salary':'4500'},headers=oh).status_code==200
        assert owner.post('/api/payroll/accrual',json={'employee_id':hourly,'period':period},headers=oh).status_code==409
        # Unpaid absence is not inferred as hours; input hours/minutes separately.
        def entry(day,shift,hours,minutes,client=reviewer,headers=rh,employee_id=hourly,note='وردية خدمة طبية مكتملة'):
            return client.post('/api/payroll/work-entries',headers=headers,
                json={'employee_id':employee_id,'work_date':day,'shift':shift,'hours':hours,'minutes':minutes,'note':note})
        assert entry(day,'morning',24,1).status_code==400
        assert entry(day,'morning',0,0).status_code==400
        assert entry(day,'morning',8.5,0).status_code==422
        assert entry(day,'morning',8,30,client=clerk,headers=ch).status_code==403
        assert entry(day,'morning',8,30,client=viewer,headers=vh).status_code==403
        a=entry(day,'morning',8,30)
        assert a.status_code==200,a.text
        a_id=a.json()['id']
        assert entry(day,'morning',8,30).status_code==409
        # An employee cannot record hours for a monthly staff member.
        assert entry(day,'morning',8,0,employee_id=monthly).status_code==409
        assert entry(day,'morning',8,0,employee_id=not_set).status_code==409
        assert owner.post('/api/payroll/accrual',json={'employee_id':hourly,'period':period},headers=oh).status_code==409
        assert reviewer.post(f'/api/payroll/work-entries/{a_id}/decision',json={'decision':'approve'},headers=rh).status_code==403
        assert clerk.post(f'/api/payroll/work-entries/{a_id}/decision',json={'decision':'approve'},headers=ch).status_code==403
        assert owner.post(f'/api/payroll/work-entries/{a_id}/decision',json={'decision':'reject','reason':'ساعات غير مطابقة لكشف الحضور'},headers=oh).status_code==200
        assert owner.post(f'/api/payroll/work-entries/{a_id}/decision',json={'decision':'approve'},headers=oh).status_code==409
        b=entry(day,'morning',8,30); assert b.status_code==200,b.text
        b_id=b.json()['id']
        assert owner.post(f'/api/payroll/work-entries/{b_id}/decision',json={'decision':'approve'},headers=oh).status_code==200
        assert owner.post(f'/api/payroll/work-entries/{b_id}/decision',json={'decision':'approve'},headers=oh).status_code==409
        # Multiple shifts must not total more than 24 hours for the same person/day.
        assert entry(day,'evening',16,0).status_code==409
        # An approved shift can be voided ONLY before salary accrual.
        r=owner.post(f'/api/payroll/work-entries/{b_id}/void',json={'reason':'كشف الحضور الفعلي يختلف عن البيانات'},headers=oh)
        assert r.status_code==200,(r.status_code,r.text)
        b=entry(day,'morning',8,30)
        assert b.status_code==200; b_id=b.json()['id']
        assert owner.post(f'/api/payroll/work-entries/{b_id}/decision',json={'decision':'approve'},headers=oh).status_code==200
        c=entry('2026-10-14','evening',7,15)
        assert c.status_code==200,c.text
        c_id=c.json()['id']
        # Some approved hours are not enough while other hours remain pending.
        assert owner.post('/api/payroll/accrual',json={'employee_id':hourly,'period':period},headers=oh).status_code==409
        assert owner.post('/api/periods/close',json={'period':period},headers=oh).status_code==409
        assert owner.post(f'/api/payroll/work-entries/{c_id}/decision',json={'decision':'approve'},headers=oh).status_code==200
        assert owner.post('/api/periods/close',json={'period':period},headers=oh).status_code==409 # not accrued
        before=owner.get('/api/payroll?period='+period).json()
        worker=next(v for v in before['items'] if v['id']==hourly)
        assert worker['pay_type']=='hourly' and worker['hourly_rate_piasters']==7555
        assert worker['approved_work_minutes']==945 and worker['approved_work_entries']==2
        assert worker['estimated_base_piasters']==118991,worker
        assert next(v for v in before['items'] if v['id']==monthly)['monthly_piasters']==450000
        assert next(v for v in before['items'] if v['id']==not_set)['pay_type'] is None
        assert hourly_wage(7555,945)==118991
        assert hourly_wage(1,30)==1 # half-up
        a=owner.post('/api/payroll/accrual',headers=oh,json={'employee_id':hourly,'period':period,'additions':'100','deductions':'25'})
        assert a.status_code==200,a.text
        assert a.json()['base_piasters']==118991 and a.json()['net_piasters']==126491
        b=owner.post('/api/payroll/accrual',headers=oh,json={'employee_id':monthly,'period':period,'additions':'250','deductions':'100'})
        assert b.status_code==200 and b.json()['net_piasters']==465000,b.text
        # New payroll requires reviewer signoff before report recognition or cash payment.
        for accrual_response in (a,b):
            ident=accrual_response.json()['id']
            assert owner.post(f'/api/payroll/accrual/{ident}/decision',headers=oh,json={'decision':'approve'}).status_code==403
            signed=reviewer.post(f'/api/payroll/accrual/{ident}/decision',headers=rh,json={'decision':'approve'})
            assert signed.status_code==200,signed.text
        assert entry('2026-10-15','morning',3,0).status_code==409
        assert owner.post(f'/api/payroll/work-entries/{b_id}/void',json={'reason':'سبب التعديل بعد اعتماد المرتب'},headers=oh).status_code==409
        assert owner.post('/api/payroll/accrual',json={'employee_id':hourly,'period':period},headers=oh).status_code==409
        assert owner.post(f'/api/employees/{hourly}/salary-term',json={'month':period,'pay_type':'hourly','hourly_rate':'90'},headers=oh).status_code==409
        assert owner.post(f'/api/employees/{hourly}/salary-term',json={'month':'2026-11','pay_type':'hourly','hourly_rate':'90'},headers=oh).status_code==200
        with connect() as db:
            s=db.execute('SELECT pay_type,hourly_rate_piasters,worked_minutes,work_entries_count,base_piasters FROM payroll_accruals WHERE employee_id=?',(hourly,)).fetchone()
            assert tuple(s)==('hourly',7555,945,2,118991),tuple(s)
            assert db.execute('SELECT count(*) FROM payroll_work_entries WHERE employee_id=? AND status=?',(hourly,'approved')).fetchone()[0]==2
        after=owner.get('/api/payroll?period='+period).json()
        assert next(v for v in after['items'] if v['id']==hourly)['hourly_rate_piasters']==7555
        assert next(v for v in owner.get('/api/payroll?period=2026-11').json()['items'] if v['id']==hourly)['hourly_rate_piasters']==9000
        assert owner.get('/api/payroll/work-entries?period='+period).json()['pending_count']==0
        assert clerk.get('/api/payroll/work-entries?period='+period).status_code==403
        assert viewer.get('/api/payroll/work-entries?period='+period).status_code==403
        assert clerk.get('/api/payroll/work-entries/export.csv?period='+period).status_code==403
        hours_csv=owner.get('/api/payroll/work-entries/export.csv?period='+period)
        assert hours_csv.status_code==200 and '2026-10-14' in hours_csv.content.decode('utf-8-sig')
        assert 'كود الموظف' in hours_csv.content.decode('utf-8-sig')
        export=owner.get('/api/payroll/export.csv?period='+period)
        assert export.status_code==200 and 'hourly' in export.content.decode('utf-8-sig')
        report=owner.get('/api/reports?month='+period)
        assert report.status_code==200 and report.json()['approved_payroll_accruals_piasters']==591491
        # Hourly accrual is payable by the ordinary financial voucher/maker-checker path.
        look=owner.get('/api/lookups').json()
        bank=next(f['id'] for f in look['funds'] if f['code']=='bank')
        reviewer_id=next(x['id'] for x in owner.get('/api/users').json() if x['username']=='reviewer')
        assert owner.post('/api/fund-access',headers=oh,json={'user_id':reviewer_id,'fund_id':bank,'can_submit':True,
             'reason':'تفويض المراجع بإنشاء سند المرتبات للاختبار'}).status_code==200
        salary_category=next(k['id'] for k in look['categories'] if k['code']=='salary_payment')
        department=look['departments'][0]['id']
        assert owner.post(f'/api/funds/{bank}/opening',json={'amount':'5000'},headers=oh).status_code==200
        def payment(amount):
            return reviewer.post('/api/vouchers',headers=rh,json={
                'date':'2026-10-15','kind':'payment','from_fund_id':bank,'shift':'central',
                'employee_id':hourly,'salary_period':period,'category_id':salary_category,'department_id':department,
                'amount':amount,'description':'سند دفع أجرة الساعة التجريبية'})
        pay=payment('600');assert pay.status_code==200,pay.text
        pid=pay.json()['id']
        done=owner.post(f'/api/vouchers/{pid}/decision',json={'decision':'approve'},headers=oh)
        assert done.status_code==200,done.text
        due=owner.get('/api/payroll?period='+period).json()
        assert next(v for v in due['items'] if v['id']==hourly)['due_piasters']==66491
        excess=payment('700');assert excess.status_code==200,excess.text
        exid=excess.json()['id']
        assert owner.post(f'/api/vouchers/{exid}/decision',json={'decision':'approve'},headers=oh).status_code==409
        assert owner.post(f'/api/vouchers/{exid}/decision',json={'decision':'reject','reason':'قيمة أعلى من المستحق المتبقي'},headers=oh).status_code==200
        assert owner.post('/api/periods/close',headers=oh,json={'period':period}).status_code==409  # bank must be reconciled
        from bank_test_helpers import signoff_bank_month
        signoff_bank_month(owner,oh,reviewer,rh,bank,period)
        from opening_test_helpers import approve_all_openings
        approve_all_openings(owner,oh,reviewer,rh,period)
        # Test clock only: emulate period already completed; production rejects current/future closes.
        with patch('app.current_month', return_value='9999-12'):
            assert owner.post('/api/periods/close',json={'period':period},headers=oh).status_code==200
        assert owner.post('/api/payroll/work-entries',json={'employee_id':hourly,'work_date':'2026-10-16','shift':'morning','hours':8,'minutes':0,'note':'لا يمكن بعد الإقفال'},headers=oh).status_code==409
        print('PASS — mixed hourly+monthly payroll, minute accuracy, independent approvals, no duplicates, immutable snapshots, closed month and roles')

if __name__=='__main__':run()
