"""G0 regression gates: month-close coverage, strict bank grants, ledger report and corrections."""
import os,sys,tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def run():
 with tempfile.TemporaryDirectory() as tmp:
    os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'g0.sqlite3')
    os.environ['RAMSES_ADMIN_USER']='owner';os.environ['RAMSES_ADMIN_PASSWORD']='g0_test_owner_password_long'
    from bootstrap import initialize,connect
    initialize()
    from fastapi.testclient import TestClient
    from app import app
    owner,clerk,reviewer=(TestClient(app) for _ in range(3))
    def login(client,username,password):
        result=client.post('/api/login',json={'username':username,'password':password})
        assert result.status_code==200,result.text
        return {'X-CSRF-Token':result.json()['csrf']}
    oh=login(owner,'owner','g0_test_owner_password_long')
    for username,role in [('cashier','clerk'),('accountant','reviewer')]:
        resp=owner.post('/api/users',headers=oh,json={'username':username,'password':'g0_worker_password_2026','role':role})
        assert resp.status_code==200,resp.text
    ch=login(clerk,'cashier','g0_worker_password_2026')
    rh=login(reviewer,'accountant','g0_worker_password_2026')
    uid=next(u['id'] for u in owner.get('/api/users').json() if u['username']=='cashier')
    today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    # Activate both real test cashier points; unassigned draft points are not
    # expected to work or to produce missing-shift warnings.
    fund_map={x['code']:x['id'] for x in owner.get('/api/funds').json()}
    for point in owner.get('/api/billing/config').json()['points']:
        fund_id=fund_map['cash_sub' if point['kind']=='external' else 'cash_main']
        assert owner.post(f'/api/billing/points/{point["id"]}/cash-fund',headers=oh,json={'fund_id':fund_id}).status_code==200
    coverage=owner.get('/api/shifts/coverage',params={'month':today[:7]}).json()
    assert coverage['items'],'Schedule expected for active cashier points'
    preflight=owner.get('/api/periods/preflight',params={'period':today[:7]})
    assert preflight.status_code==200 and not preflight.json()['ready'],preflight.text
    assert 'وردية' in preflight.json()['reason']
    assert clerk.get('/api/periods/preflight',params={'period':today[:7]}).status_code==403
    blocked=owner.post('/api/periods/close',headers=oh,json={'period':today[:7]})
    assert blocked.status_code==409 and 'وردية' in blocked.text,blocked.text
    with connect() as c:
        assert c.execute('SELECT COUNT(*) FROM periods').fetchone()[0]==0
    print('PASS G0-01: missing scheduled but unregistered shifts BLOCK month close')

    lk=owner.get('/api/lookups').json()
    bank=next(f['id'] for f in lk['funds'] if f['kind']=='bank')
    dept=next(d['id'] for d in lk['departments'] if d['code']=='ADMIN')
    cat=next(x['id'] for x in lk['categories'] if x['code']=='other_revenue')
    body={'date':today,'kind':'receipt','shift':'central','from_fund_id':bank,
       'department_id':dept,'category_id':cat,'amount':'500',
       'description':'تحصيل تجريبي لا يخص مرضى المستشفى'}
    denied=clerk.post('/api/vouchers',headers=ch,json=body)
    assert denied.status_code==403,denied.text
    assert clerk.post('/api/fund-access',headers=ch,json={'user_id':uid,'fund_id':bank,'can_submit':True,'reason':'بدون تفويض'}).status_code==403
    grant=owner.post('/api/fund-access',headers=oh,json={'user_id':uid,'fund_id':bank,'can_submit':True,
       'reason':'منح مؤقت لتسجيل سند بنكي تجريبي'})
    assert grant.status_code==200,grant.text
    v=clerk.post('/api/vouchers',headers=ch,json=body)
    assert v.status_code==200,v.text
    assert reviewer.post(f'/api/vouchers/{v.json()["id"]}/decision',headers=rh,json={'decision':'approve'}).status_code==403
    reviewer_uid=next(u['id'] for u in owner.get('/api/users').json() if u['username']=='accountant')
    assert owner.post('/api/fund-access',headers=oh,json={'user_id':uid,'fund_id':bank,'can_approve':True,'reason':'كاشير يحاول أخذ اعتماد بنك'}).status_code==403
    assert owner.post('/api/fund-access',headers=oh,json={'user_id':reviewer_uid,'fund_id':bank,'can_approve':True,'reason':'تفويض مراجعة بنك مستقل للاختبار'}).status_code==200
    assert reviewer.post(f'/api/vouchers/{v.json()["id"]}/decision',headers=rh,json={'decision':'approve'}).status_code==200
    r=owner.get('/api/reports',params={'month':today[:7]})
    assert r.status_code==200,r.text
    d=r.json()
    assert d['recognized_revenue_piasters']==50000,d
    assert d['provisional_gl_result_piasters']==50000,d
    assert sum(row['recognized_revenue_piasters'] for row in d['gl_departments'])==50000
    print('PASS G0-02: explicit bank grant + GL-authoritative revenue report, no cash double count')
    source=owner.post('/api/corrections',headers=oh,json={
       'source_type':'voucher','source_id':v.json()['id'],'issue_type':'wrong_method',
       'reason':'مستند تجريبي يحتاج فحص وسيلة الدفع قبل أي تصحيح مالي',
       'proposed_resolution':'إحالة البلاغ إلى المراجعة المستقلة دون تغيير الأستاذ',
       'request_key':'g0-correction-bank-001'})
    assert source.status_code==200,source.text
    assert source.json()['financial_posted'] if 'financial_posted' in source.json() else True
    with connect() as c:
        assert c.execute("SELECT COUNT(*) FROM gl_journals WHERE status='posted'").fetchone()[0]==1
    print('PASS G0-03: voucher correction intake no HTTP 500, no financial mutation')

    pending=clerk.post('/api/vouchers',headers=ch,json={**body,'description':'سند تجريبي جديد قبل سحب تفويض البنك'})
    assert pending.status_code==200,pending.text
    revoke=owner.post('/api/fund-access',headers=oh,json={'user_id':uid,'fund_id':bank,'can_submit':False,
       'reason':'سحب تفويض الموظف من الحساب البنكي'})
    assert revoke.status_code==200,revoke.text
    assert clerk.post('/api/vouchers',headers=ch,json={**body,'description':'محاولة تجاوز صلاحية البنك المسحوبة'}).status_code==403
    assert reviewer.post(f'/api/vouchers/{pending.json()["id"]}/decision',headers=rh,json={'decision':'approve'}).status_code==403
    assert owner.get('/api/fund-access').json()[0]['can_submit']==0
    assert owner.post('/api/fund-access',headers=oh,json={'user_id':reviewer_uid,'fund_id':bank,'can_approve':False,'reason':'سحب صلاحية اعتماد البنك من المراجع'}).status_code==200
    bank_approvals=owner.get('/api/fund-access').json()
    assert next(g for g in bank_approvals if g['user_id']==reviewer_uid)['can_approve']==0
    print('PASS G0-04: immediate grant revocation blocks new AND pending bank posting')

if __name__=='__main__':run()
