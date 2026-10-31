"""G2S month close bed-night invariant, scoped by night date not case-opening date."""
import os
import sys
import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'test.sqlite3'),RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_month_end_owner_password')
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from bed_stays import month_close_bed_issue
        from fastapi.testclient import TestClient
        owner,clerk=TestClient(app),TestClient(app)
        def ok(resp,status=200):
            assert resp.status_code==status,(resp.status_code,resp.text)
            return resp.json() if status==200 else None
        oh={'X-CSRF-Token':ok(owner.post('/api/login',json={'username':'owner','password':'synthetic_month_end_owner_password'}))['csrf']}
        ok(owner.post('/api/users',headers=oh,json={'username':'g2s_clerk','password':'synthetic_clerk_password_2026','role':'clerk'}))
        ch={'X-CSRF-Token':ok(clerk.post('/api/login',json={'username':'g2s_clerk','password':'synthetic_clerk_password_2026'}))['csrf']}
        point=next(p['id'] for p in ok(owner.get('/api/billing/config'))['points'] if p['kind']=='internal')
        with connect() as c:uid=c.execute("SELECT id FROM users WHERE username='g2s_clerk'").fetchone()[0]
        ok(owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={'user_id':uid,'active':True}))
        now=datetime.now(ZoneInfo('Africa/Cairo')).date()
        month_start=now.replace(day=1)
        prev=(month_start-timedelta(days=2)).isoformat()
        last=(month_start-timedelta(days=1)).isoformat()
        current_month=month_start.strftime('%Y-%m')
        prev_month=(month_start-timedelta(days=1)).strftime('%Y-%m')
        department=next(d['id'] for d in ok(owner.get('/api/lookups'))['departments'] if d['code']=='IPD')
        service=ok(owner.post('/api/billing/services',headers=oh,json={'code':'G2S_CROSS_MONTH_BED','name':'Synthetic cross-month bed','department_id':department}))['id']
        ok(owner.post(f'/api/billing/services/{service}/prices',headers=oh,json={'valid_from':prev,'amount':'100'}))
        bed=ok(owner.post('/api/beds/catalog',headers=oh,json={'code':'G2S-XM','name':'Synthetic cross-month bed','kind':'inpatient','service_id':service}))['id']
        pat=ok(clerk.post('/api/billing/patients',headers=ch,json={'display_name':'Synthetic month-end patient','request_id':'g2s_monthend_patient_01'}))['id']
        case=ok(clerk.post('/api/billing/cases',headers=ch,json={'patient_id':pat,'point_id':point,'kind':'inpatient','business_date':prev,'request_id':'g2s_monthend_case_0001'}))['id']
        stay=ok(owner.post(f'/api/beds/cases/{case}/admit',headers=oh,json={'bed_id':bed,'start_date':prev,'evidence_reference':'SYN-PREV-MONTH-ADMISSION','request_id':'g2s_monthend_stay_0001'}))['id']
        with connect() as c:
            issue=month_close_bed_issue(c,prev_month)
            assert issue and issue['kind']=='missing_nights' and issue['missing']==2,issue
        ok(owner.post(f'/api/beds/stays/{stay}/charge',headers=oh,json={'through_date':month_start.isoformat(),'request_id':'g2s_monthend_charge_prev'}))
        with connect() as c:
            issue=month_close_bed_issue(c,prev_month)
            assert issue and issue['kind']=='not_invoiced',issue
            assert month_close_bed_issue(c,current_month)['kind']=='missing_nights'
        # The normal preflight remains blocked independently of the admission month.
        pre=ok(owner.get(f'/api/periods/preflight?period={prev_month}'))
        assert not pre['ready'],pre
        print('PASS G2S monthly night checks: missed nights and uninvoiced nights are scoped to service month')

if __name__=='__main__':run()
