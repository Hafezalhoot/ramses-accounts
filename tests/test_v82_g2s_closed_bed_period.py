"""G2S month-lock test: no retroactive physical/financial occupancy mutation."""
import os
import sys
import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'test.sqlite3'),RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_closed_period_password')
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,clerk=TestClient(app),TestClient(app)
        def ok(resp,code=200):
            assert resp.status_code==code,(resp.status_code,resp.text,code)
            return resp.json() if code==200 else None
        oh={'X-CSRF-Token':ok(owner.post('/api/login',json={'username':'owner','password':'synthetic_closed_period_password'}))['csrf']}
        ok(owner.post('/api/users',headers=oh,json={'username':'g2s_clerk','password':'synthetic_g2s_clerk_password','role':'clerk'}))
        ch={'X-CSRF-Token':ok(clerk.post('/api/login',json={'username':'g2s_clerk','password':'synthetic_g2s_clerk_password'}))['csrf']}
        point=next(p['id'] for p in ok(owner.get('/api/billing/config'))['points'] if p['kind']=='internal')
        with connect() as c:clerk_id=c.execute("SELECT id FROM users WHERE username='g2s_clerk'").fetchone()[0]
        ok(owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={'user_id':clerk_id,'active':True}))
        first=datetime.now(ZoneInfo('Africa/Cairo')).date().replace(day=1)
        last=first-timedelta(days=1)
        old=(last-timedelta(days=2)).isoformat()
        prior_month=last.strftime('%Y-%m')
        dept=next(d['id'] for d in ok(owner.get('/api/lookups'))['departments'] if d['code']=='IPD')
        svc=ok(owner.post('/api/billing/services',headers=oh,json={'code':'G2S_LOCKED_BED','name':'Synthetic locked bed nights','department_id':dept}))['id']
        price=ok(owner.post(f'/api/billing/services/{svc}/prices',headers=oh,json={'valid_from':old,'amount':'75'}))
        bed=ok(owner.post('/api/beds/catalog',headers=oh,json={'code':'G2S-LOCKED-A','name':'Synthetic locked bed A','kind':'inpatient','service_id':svc}))['id']
        bed2=ok(owner.post('/api/beds/catalog',headers=oh,json={'code':'G2S-LOCKED-B','name':'Synthetic locked bed B','kind':'inpatient','service_id':svc}))['id']
        patients=[]
        for i in range(2):
            patients.append(ok(clerk.post('/api/billing/patients',headers=ch,json={'display_name':'Synthetic period patient','request_id':f'g2s_locked_patient_{i:04d}'}))['id'])
        cases=[]
        for i,pat in enumerate(patients):
            cases.append(ok(clerk.post('/api/billing/cases',headers=ch,json={'patient_id':pat,'point_id':point,'kind':'inpatient','business_date':old,'request_id':f'g2s_locked_case_{i:06d}'}))['id'])
        stay=ok(owner.post(f'/api/beds/cases/{cases[0]}/admit',headers=oh,json={'bed_id':bed,'start_date':old,'evidence_reference':'SYN-OLD-LOCKED-STAY-0001','request_id':'g2s_locked_admission_001'}))['id']
        with connect() as c:
            rate=c.execute('SELECT id FROM billing_service_prices WHERE service_id=?',(svc,)).fetchone()[0]
            line=c.execute('''INSERT INTO billing_case_lines
                (case_id,service_id,price_version_id,service_name_snapshot,department_id,unit_price_piasters,quantity,added_by,added_at)
                VALUES (?,?,?,?,?,?,?,?,?)''',(cases[0],svc,rate,'Synthetic locked night',dept,7500,1,1,old)).lastrowid
            c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES(?,?,?)',(prior_month,1,first.isoformat()))
            c.commit()
        # Release and transfer cannot rewrite the physical occupancy of a sealed month.
        ok(owner.post(f'/api/beds/stays/{stay}/release',headers=oh,json={
            'end_date':last.isoformat(),'evidence_reference':'SYN-OLD-RELEASE-REF-01'}),409)
        with connect() as c:
            sqls=[('''INSERT INTO bed_stays(bed_id,case_id,start_date,admission_evidence,recorded_by,recorded_at)
                     VALUES(?,?,?,?,?,?)''',(bed2,cases[1],old,'SYN-SQL-OLD-ADMIT-001',1,old)),
                  ('''INSERT INTO bed_night_charges
                     (stay_id,night_date,case_line_id,price_version_id,amount_piasters,ordered_by,ordered_at)
                     VALUES(?,?,?,?,?,?,?)''',(stay,old,line,rate,7500,1,old))]
            for sql,args in sqls:
                c.execute('BEGIN IMMEDIATE')
                try:c.execute(sql,args)
                except Exception:c.rollback()
                else:
                    c.rollback()
                    raise AssertionError('Direct SQL changed a sealed bed month')
        print('PASS G2S sealed period: release/bed insert/night insert all rejected')

if __name__=='__main__':run()
