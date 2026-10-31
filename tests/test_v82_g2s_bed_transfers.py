"""G2S transfer tests. TDD: initially fails because the endpoint is absent."""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'g2s.sqlite3'),RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_g2s_owner_password_2026')
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,clerk=TestClient(app),TestClient(app)
        def ok(resp,status=200):
            assert resp.status_code==status,(resp.status_code,resp.text,status)
            return resp.json() if status==200 else None
        oh={'X-CSRF-Token':ok(owner.post('/api/login',json={'username':'owner','password':'synthetic_g2s_owner_password_2026'}))['csrf']}
        ok(owner.post('/api/users',headers=oh,json={'username':'g2s_clerk','password':'synthetic_g2s_employee_password','role':'clerk'}))
        ch={'X-CSRF-Token':ok(clerk.post('/api/login',json={'username':'g2s_clerk','password':'synthetic_g2s_employee_password'}))['csrf']}
        point=next(p['id'] for p in ok(owner.get('/api/billing/config'))['points'] if p['kind']=='internal')
        with connect() as c:
            user_id=c.execute("SELECT id FROM users WHERE username='g2s_clerk'").fetchone()[0]
        ok(owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={'user_id':user_id,'active':True}))
        department=next(d['id'] for d in ok(owner.get('/api/lookups'))['departments'] if d['code']=='IPD')
        now=datetime.now(ZoneInfo('Africa/Cairo')).date()
        start=(now-timedelta(days=4)).isoformat()
        transfer=(now-timedelta(days=2)).isoformat()
        def new_service(code,price):
            sid=ok(owner.post('/api/billing/services',headers=oh,json={'code':code,'name':'Synthetic G2S daily tariff','department_id':department}))['id']
            ok(owner.post(f'/api/billing/services/{sid}/prices',headers=oh,json={'valid_from':start,'amount':str(price)}))
            return sid
        service_a,service_b=new_service('G2S_STAY_A',110),new_service('G2S_STAY_B',230)
        bed_a=ok(owner.post('/api/beds/catalog',headers=oh,json={'code':'G2S-A','name':'Synthetic first bed','kind':'inpatient','service_id':service_a}))['id']
        bed_b=ok(owner.post('/api/beds/catalog',headers=oh,json={'code':'G2S-B','name':'Synthetic second bed','kind':'inpatient','service_id':service_b}))['id']
        patient=ok(clerk.post('/api/billing/patients',headers=ch,json={'display_name':'Synthetic transfer patient','request_id':'g2s_patient_00000001'}))['id']
        case=ok(clerk.post('/api/billing/cases',headers=ch,json={'patient_id':patient,'point_id':point,'kind':'inpatient','business_date':start,'request_id':'g2s_case_00000000001'}))['id']
        old=ok(owner.post(f'/api/beds/cases/{case}/admit',headers=oh,json={'bed_id':bed_a,'start_date':start,'evidence_reference':'SYN-TRANSFER-ADMISSION-01','request_id':'g2s_admission_00000001'}))['id']
        path=f'/api/beds/stays/{old}/transfer'
        payload={'to_bed_id':bed_b,'transfer_date':transfer,'evidence_reference':'SYN-BED-TRANSFER-REF-001','request_id':'g2s_transfer_00000001'}
        assert clerk.post(path,headers=ch,json=payload).status_code==403
        ok(owner.post(path,headers=oh,json={**payload,'to_bed_id':bed_a}),409)
        result=ok(owner.post(path,headers=oh,json=payload))
        assert result['from_stay_id']==old and result['to_stay_id']!=old,result
        new=result['to_stay_id']
        replay=ok(owner.post(path,headers=oh,json=payload))
        assert replay['replayed'] is True and replay['to_stay_id']==new,replay
        ok(owner.post(path,headers=oh,json={**payload,'request_id':'g2s_transfer_again00001'}),409)
        info=ok(owner.get(f'/api/beds/cases/{case}'))
        assert info['active_stay']['id']==new,info
        assert info['stays'][0]['end_date']==transfer and info['stays'][1]['start_date']==transfer,info
        assert len(info['transfers'])==1 and info['transfers'][0]['id']==result['id'],info
        first=ok(owner.post(f'/api/beds/stays/{old}/charge',headers=oh,json={'through_date':now.isoformat(),'request_id':'g2s_charge_old00000001'}))
        second=ok(owner.post(f'/api/beds/stays/{new}/charge',headers=oh,json={'through_date':now.isoformat(),'request_id':'g2s_charge_new00000001'}))
        assert first['created_nights']==2 and first['total_piasters']==22000,first
        assert second['created_nights']==2 and second['total_piasters']==46000,second
        with connect() as c:
            dates=list(c.execute('SELECT stay_id,night_date,amount_piasters FROM bed_night_charges ORDER BY night_date'))
            assert [r[2] for r in dates]==[11000,11000,23000,23000],dates
            tr=c.execute('SELECT * FROM bed_transfers').fetchone()
            assert tr['from_stay_id']==old and tr['to_stay_id']==new,tr
            assert not c.execute('SELECT 1 FROM gl_journals').fetchone()
            for sql in ('UPDATE bed_transfers SET transfer_date=? WHERE id=?','DELETE FROM bed_transfers WHERE id=?'):
                try:
                    c.execute(sql,(now.isoformat(),tr['id']) if sql.startswith('UPDATE') else (tr['id'],))
                except Exception:c.rollback()
                else:raise AssertionError('Bed transfer audit log was mutable')
        ok(owner.post(f'/api/beds/stays/{new}/transfer',headers=oh,json={**payload,'transfer_date':start,'request_id':'g2s_backdated_transfer01'}),409)
        print('PASS G2S transfer: atomic, immutable, authorized, idempotent, priced split, zero GL')

if __name__=='__main__':run()
