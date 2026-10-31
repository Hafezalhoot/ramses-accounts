"""V7.5: explicit payroll adjustments, dual approvals, safe cash/close gates."""
from unittest.mock import patch
import os
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'review.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='nonproduction_owner_password_123'
        os.environ.pop('RAMSES_REQUIRE_PAYMENT_EVIDENCE',None)
        from bootstrap import initialize,connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app,payroll_due
        owner,reviewer,clerk,viewer=(TestClient(app) for _ in range(4))
        def login(client,username,password):
            resp=client.post('/api/login',json={'username':username,'password':password})
            assert resp.status_code==200,resp.text
            return {'X-CSRF-Token':resp.json()['csrf']}
        oh=login(owner,'owner','nonproduction_owner_password_123')
        for name,role in [('reviewer','reviewer'),('clerk','clerk'),('viewer','viewer')]:
            r=owner.post('/api/users',headers=oh,json={'username':name,'password':'test_password_1234567','role':role})
            assert r.status_code==200,r.text
        rh=login(reviewer,'reviewer','test_password_1234567')
        ch=login(clerk,'clerk','test_password_1234567')
        vh=login(viewer,'viewer','test_password_1234567')
        def employee(code,paytype,amount):
            create=owner.post('/api/employees',headers=oh,json={'code':code,'name':'موظف '+code})
            assert create.status_code==200,create.text
            eid=create.json()['id']
            terms={'month':'2026-10','pay_type':paytype}
            terms['hourly_rate' if paytype=='hourly' else 'monthly_salary']=amount
            r=owner.post(f'/api/employees/{eid}/salary-term',headers=oh,json=terms)
            assert r.status_code==200,r.text
            return eid
        monthly=employee('M001','monthly','4500')
        hourly=employee('H001','hourly','80')
        period='2026-10'
        def adj(client,h,eid,kind,amount,note='مراجعة كشف حضور وطلب إدارة شؤون العاملين'):
            return client.post('/api/payroll/adjustments',headers=h,
                   json={'employee_id':eid,'period':period,'kind':kind,'amount':amount,'note':note})
        assert adj(clerk,ch,monthly,'bonus','100').status_code==403
        assert adj(owner,oh,monthly,'bonus','-10').status_code==400
        assert adj(owner,oh,monthly,'nonsense','10').status_code==400
        assert adj(owner,oh,monthly,'bonus','100',note='x').status_code==400
        bonus=adj(owner,oh,monthly,'bonus','100');assert bonus.status_code==200,bonus.text
        bonus_id=bonus.json()['id']
        assert owner.post(f'/api/payroll/adjustments/{bonus_id}/decision',headers=oh,json={'decision':'approve'}).status_code==403
        assert owner.post('/api/payroll/accrual',headers=oh,json={'employee_id':monthly,'period':period}).status_code==409
        assert reviewer.post(f'/api/payroll/adjustments/{bonus_id}/decision',headers=rh,json={'decision':'approve'}).status_code==200
        assert reviewer.post(f'/api/payroll/adjustments/{bonus_id}/decision',headers=rh,json={'decision':'approve'}).status_code==409
        other=adj(owner,oh,monthly,'lateness_deduction','75.25');oid=other.json()['id']
        assert reviewer.post(f'/api/payroll/adjustments/{oid}/decision',headers=rh,json={'decision':'approve'}).status_code==200
        leave=adj(reviewer,rh,monthly,'paid_leave_credit','50');lid=leave.json()['id']
        assert reviewer.post(f'/api/payroll/adjustments/{lid}/decision',headers=rh,json={'decision':'approve'}).status_code==403
        assert owner.post(f'/api/payroll/adjustments/{lid}/decision',headers=oh,json={'decision':'approve'}).status_code==200
        rejected=adj(owner,oh,monthly,'absence_deduction','200');rid=rejected.json()['id']
        assert reviewer.post(f'/api/payroll/adjustments/{rid}/decision',headers=rh,
                             json={'decision':'reject','reason':'خاطئ - يوم الغياب كان بإذن معتمد'}).status_code==200
        res=owner.post(f'/api/payroll/adjustments/{rid}/void',headers=oh,json={'reason':'مرفوض'})
        assert res.status_code==400,(res.status_code,res.text)
        hbonus=adj(owner,oh,hourly,'overtime_premium','37.50')
        assert reviewer.post(f'/api/payroll/adjustments/{hbonus.json()["id"]}/decision',headers=rh,
                             json={'decision':'approve'}).status_code==200
        w=reviewer.post('/api/payroll/work-entries',headers=rh,
            json={'employee_id':hourly,'work_date':'2026-10-05','shift':'morning','hours':8,'minutes':15,
                  'note':'8:15 ساعة مدرجة كأساس دون احتساب إضافي تلقائي'})
        assert w.status_code==200,w.text
        assert owner.post(f'/api/payroll/work-entries/{w.json()["id"]}/decision',headers=oh,
                          json={'decision':'approve'}).status_code==200
        # All approved adjustments are included in the frozen accrual total, not computed by assumed HR policy.
        m=owner.post('/api/payroll/accrual',headers=oh,
                     json={'employee_id':monthly,'period':period,'additions':'25','deductions':'10'})
        assert m.status_code==200,m.text
        mid=m.json()['id'];assert m.json()['net_piasters']==458975
        assert m.json()['signoff_status']=='pending'
        h=owner.post('/api/payroll/accrual',headers=oh,json={'employee_id':hourly,'period':period})
        assert h.status_code==200,h.text
        hid=h.json()['id'];assert h.json()['net_piasters']==69750
        assert adj(owner,oh,monthly,'bonus','10').status_code==409
        assert owner.post(f'/api/payroll/adjustments/{bonus_id}/void',headers=oh,
                          json={'reason':'محاولة إلغاء بعد إعداد الاستحقاق'}).status_code==409
        assert viewer.get('/api/payroll/adjustments?period='+period).status_code==403
        assert clerk.get('/api/payroll/adjustments?period='+period).status_code==403
        assert viewer.post(f'/api/payroll/accrual/{mid}/decision',headers=vh,
                           json={'decision':'approve'}).status_code==403
        assert owner.post(f'/api/payroll/accrual/{mid}/decision',headers=oh,
                          json={'decision':'approve'}).status_code==403
        with connect() as db:
            assert payroll_due(db,monthly,period) is None
        assert owner.get('/api/payroll?period='+period).json()['due_total_piasters']==0
        assert owner.post('/api/periods/close',headers=oh,json={'period':period}).status_code==409
        look=owner.get('/api/lookups').json()
        bank=next(x['id'] for x in look['funds'] if x['code']=='bank')
        clerk_id=next(x['id'] for x in owner.get('/api/users').json() if x['username']=='clerk')
        assert owner.post('/api/fund-access',headers=oh,json={'user_id':clerk_id,'fund_id':bank,'can_submit':True,
             'reason':'تفويض دفع أجور البنك للاختبارات فقط'}).status_code==200
        reviewer_id=next(x['id'] for x in owner.get('/api/users').json() if x['username']=='reviewer')
        assert owner.post('/api/fund-access',headers=oh,json={'user_id':reviewer_id,'fund_id':bank,'can_approve':True,
             'reason':'تفويض مراجعة سندات الرواتب البنكية فقط'}).status_code==200
        cat=next(x['id'] for x in look['categories'] if x['code']=='salary_payment')
        dept=look['departments'][0]['id']
        assert owner.post(f'/api/funds/{bank}/opening',headers=oh,json={'amount':'20000'}).status_code==200
        def pay(amount,eid):
            return clerk.post('/api/vouchers',headers=ch,json={
                 'date':'2026-10-25','kind':'payment','from_fund_id':bank,'shift':'central',
                 'category_id':cat,'department_id':dept,'employee_id':eid,'salary_period':period,
                 'amount':amount,'description':'صرف مستحقات العاملين بعد المراجعة'})
        p=pay('100',monthly);pid=p.json()['id']
        assert reviewer.post(f'/api/vouchers/{pid}/decision',headers=rh,
                             json={'decision':'approve'}).status_code==409
        assert owner.post('/api/payroll/allocate-advance',headers=oh,
                          json={'employee_id':monthly,'period':period,'amount':'10'}).status_code==409
        # Reviewer explicitly rejects the first payroll, owner corrects it, then reviewer signs the corrected snapshot.
        assert reviewer.post(f'/api/payroll/accrual/{mid}/decision',headers=rh,
                             json={'decision':'reject','reason':'إعادة مراجعة الإضافات والخصومات'}).status_code==200
        assert reviewer.post(f'/api/payroll/accrual/{mid}/decision',headers=rh,
                             json={'decision':'approve'}).status_code==409
        # Pending payment prevents correcting: reject pending voucher first.
        assert owner.post(f'/api/payroll/accrual/{mid}/correct',headers=oh,
                          json={'additions':'30','deductions':'10','reason':'تصحيح المراجعة المطلوبة من الإدارة'}).status_code==409
        assert reviewer.post(f'/api/vouchers/{pid}/decision',headers=rh,
                             json={'decision':'reject','reason':'رفض السند قبل التصحيح'}).status_code==200
        correction=owner.post(f'/api/payroll/accrual/{mid}/correct',headers=oh,
                              json={'additions':'30','deductions':'10','reason':'تصحيح المراجعة المطلوبة من الإدارة'})
        assert correction.status_code==200,correction.text
        assert correction.json()['net_piasters']==459475
        assert reviewer.post(f'/api/payroll/accrual/{mid}/decision',headers=rh,json={'decision':'approve'}).status_code==200
        assert reviewer.post(f'/api/payroll/accrual/{hid}/decision',headers=rh,json={'decision':'approve'}).status_code==200
        assert owner.get('/api/payroll?period='+period).json()['due_total_piasters']==459475+69750
        payroll=owner.get('/api/payroll?period='+period).json()['items']
        mrow=next(x for x in payroll if x['id']==monthly)
        assert mrow['snapshot_adjustment_additions_piasters']==15000
        assert mrow['snapshot_adjustment_deductions_piasters']==7525
        assert mrow['signoff_status']=='approved'
        approved=pay('100',monthly);assert approved.status_code==200
        assert reviewer.post(f'/api/vouchers/{approved.json()["id"]}/decision',headers=rh,
                             json={'decision':'approve'}).status_code==200
        assert owner.get('/api/payroll?period='+period).json()['due_total_piasters']==459475+69750-10000
        csv=owner.get('/api/payroll/export.csv?period='+period)
        assert csv.status_code==200 and 'signoff' not in csv.text and 'approved' in csv.text
        # Signed-off status is visible in the private mirror and does not imply a real Google connection.
        from google_sync import datasets_for
        with connect() as db:
            mirror=datasets_for(db)['Ramses_Payroll']
        assert len(mirror[0])==15 and any(row[-1]=='approved' for row in mirror[1:])
        assert owner.post('/api/periods/close',headers=oh,json={'period':period}).status_code==409  # bank must be reconciled
        from bank_test_helpers import signoff_bank_month
        signoff_bank_month(owner,oh,reviewer,rh,bank,period)
        from opening_test_helpers import approve_all_openings
        approve_all_openings(owner,oh,reviewer,rh,period)
        # Test clock only: emulate period already completed; production rejects current/future closes.
        with patch('app.current_month', return_value='9999-12'):
            assert owner.post('/api/periods/close',headers=oh,json={'period':period}).status_code==200
        assert owner.post('/api/payroll/adjustments',headers=oh,json={
             'employee_id':monthly,'period':period,'kind':'bonus','amount':'30','note':'تجربة إضافة بعد الإقفال'}).status_code==409
        print('PASS - payroll V7.5 manual approved additions/deductions, separate signoffs, blocking payments, audit, CSV, mirror and month close')

if __name__=='__main__':run()
