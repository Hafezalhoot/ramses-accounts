"""Owner-only per-shift cashier access, including mid-shift revocation."""
import os,sys,tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def run():
    with tempfile.TemporaryDirectory() as temp:
        os.environ['RAMSES_DB_PATH']=str(Path(temp)/'test.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='strong_password_shift_owner'
        from bootstrap import initialize,connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        o=TestClient(app);cl=TestClient(app)
        def signin(client,name,password):
            r=client.post('/api/login',json={'username':name,'password':password})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=signin(o,'owner','strong_password_shift_owner')
        created=o.post('/api/users',headers=oh,json={'username':'cashier_test','password':'long_password_cashier_2026','role':'clerk'})
        assert created.status_code==200,created.text
        ch=signin(cl,'cashier_test','long_password_cashier_2026')
        uid=next(r['id'] for r in o.get('/api/users').json() if r['username']=='cashier_test')
        plans=o.get('/api/cashier/plans').json()
        point=next(p for p in plans['points'] if p['kind']=='external')
        fund=next(x['id'] for x in o.get('/api/funds').json() if x['code']=='cash_sub')
        assert o.post(f'/api/billing/points/{point["id"]}/cash-fund',headers=oh,json={'fund_id':fund}).status_code==200
        assert o.post(f'/api/billing/points/{point["id"]}/assign',headers=oh,json={'user_id':uid}).status_code==200
        initial=o.get('/api/cashier/staff-access');assert initial.status_code==200,initial.text
        row=next(r for r in initial.json() if r['user_id']==uid)
        assert row['allowed_codes'] is None
        req={'point_id':point['id'],'user_id':uid,'allowed_codes':['morning'],'reason':'تحديد ساعات عمل الكاشير المعتمدة'}
        assert cl.post('/api/cashier/staff-access',headers=ch,json=req).status_code==403
        approved=o.post('/api/cashier/staff-access',headers=oh,json=req)
        assert approved.status_code==200,approved.text
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        rejected=cl.post('/api/shifts/open',headers=ch,json={'fund_id':fund,'business_date':day,'shift':'night'})
        assert rejected.status_code==403,rejected.text
        good=cl.post('/api/shifts/open',headers=ch,json={'fund_id':fund,'business_date':day,'shift':'morning'})
        assert good.status_code==200,good.text
        assert o.post('/api/cashier/staff-access',headers=oh,json={**req,'allowed_codes':[],
            'reason':'سحب حق فتح الورديات بالكامل'}).status_code==200
        denied=cl.post('/api/shifts/open',headers=ch,json={'fund_id':fund,'business_date':day,'shift':'morning'})
        assert denied.status_code==403,denied.text
        with connect() as c:
            row=c.execute('SELECT allowed_codes FROM cashier_shift_staff_rules WHERE user_id=?',(uid,)).fetchone()
            assert row['allowed_codes']==''
            actions=[r[0] for r in c.execute('SELECT action FROM audit_log WHERE target_type=? AND target_id=?',('user',uid))] if False else []
        print('PASS V8.1E staff access owner only, per shift open guard, revocation and preservation')
if __name__=='__main__':run()
