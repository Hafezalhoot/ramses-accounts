"""Salary accrual corrections must be auditable and stop once payroll is in flight."""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'payroll.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='test_super_long_password_1'
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,clerk,reviewer,viewer=(TestClient(app) for _ in range(4))
        def sign(c,n,p):
            r=c.post('/api/login',json={'username':n,'password':p})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=sign(owner,'owner','test_super_long_password_1')
        for username,role in [('cashier','clerk'),('control','reviewer'),('observer','viewer')]:
            assert owner.post('/api/users',headers=oh,json={'username':username,'password':'long_secret_for_test_2026','role':role}).status_code==200
        ch=sign(clerk,'cashier','long_secret_for_test_2026')
        rh=sign(reviewer,'control','long_secret_for_test_2026')
        vh=sign(viewer,'observer','long_secret_for_test_2026')
        d=owner.post('/api/employees',json={'name':'موظف إختبار تجريبي','code':'PAY007'},headers=oh)
        assert d.status_code==200,d.text
        emp=d.json()['id']
        month=datetime.now().astimezone().date().isoformat()[:7]
        assert owner.post(f'/api/employees/{emp}/salary-term',headers=oh,
            json={'month':month,'monthly_salary':'3000'}).status_code==200
        a=owner.post('/api/payroll/accrual',headers=oh,
            json={'employee_id':emp,'period':month,'additions':'100','deductions':'50'})
        assert a.status_code==200,a.text
        aid=a.json()['id']
        assert a.json()['net_piasters']==305000
        d=owner.get('/api/payroll?period='+month).json()
        employee=next(x for x in d['items'] if x['id']==emp)
        assert employee['can_correct'] and employee['accrual_id']==aid
        assert clerk.post(f'/api/payroll/accrual/{aid}/correct',headers=ch,
                json={'additions':'100','deductions':'80','reason':'أمر إداري موثق للمراجعة'}).status_code==403
        assert owner.post(f'/api/payroll/accrual/{aid}/correct',headers=oh,
                json={'additions':'0','deductions':'3500','reason':'خصومات أكثر من الراتب'}).status_code==400
        new=owner.post(f'/api/payroll/accrual/{aid}/correct',headers=oh,
                json={'additions':'200','deductions':'75','reason':'تصحيح مكافأة وخصم قبل صرف الراتب'})
        assert new.status_code==200,new.text
        assert new.json()['net_piasters']==312500
        with connect() as db:
            corr=db.execute('SELECT old_net,new_net,reason FROM payroll_accrual_corrections WHERE accrual_id=?',(aid,)).fetchone()
            assert corr['old_net']==305000 and corr['new_net']==312500
        assert owner.post(f'/api/payroll/accrual/{aid}/correct',headers=oh,
                json={'additions':'200','deductions':'75','reason':'نفس المبلغ دون تغيير'}).status_code==409
        assert viewer.get('/api/payroll/export.csv?period='+month).status_code==403
        assert viewer.get('/api/payroll?period='+month).status_code==403
        export=owner.get('/api/payroll/export.csv?period='+month)
        assert export.status_code==200 and 'PAY007' in export.text and '312500' in export.text
        assert reviewer.get('/api/payroll/export.csv?period='+month).status_code==200
        lk=owner.get('/api/lookups').json()
        fund=lk['funds'][0]['id'];dept=lk['departments'][0]['id']
        cat=next(x['id'] for x in lk['categories'] if x['code']=='salary_payment')
        pending=clerk.post('/api/vouchers',headers=ch,json={
             'date':month+'-10','kind':'payment','department_id':dept,'category_id':cat,
             'from_fund_id':fund,'shift':'central','amount':'300','description':'صرف راتب قيد التجربة',
             'employee_id':emp,'salary_period':month})
        assert pending.status_code==200,pending.text
        assert owner.get('/api/payroll?period='+month).json()['items'][0]['can_correct'] is False
        assert owner.post(f'/api/payroll/accrual/{aid}/correct',headers=oh,
                json={'additions':'250','deductions':'50','reason':'يجب الرفض مع وجود سند راتب معلق'}).status_code==409
        assert reviewer.post(f'/api/vouchers/{pending.json()["id"]}/decision',headers=rh,
                json={'decision':'reject','reason':'رفض المستند قبل الإصدار'}).status_code==200
        assert owner.get('/api/payroll?period='+month).json()['items'][0]['can_correct'] is True
        print('PASS — salary corrections audited, CSV protected, pending salary freezes revisions, reject restores editability')
if __name__=='__main__':run()
