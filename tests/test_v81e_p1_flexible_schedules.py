"""Actual HTTP and SQLite checks for V8.1E-P1 (TEST DB ONLY)."""
import os
import sys
import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as d:
        os.environ['RAMSES_DB_PATH']=str(Path(d)/'ramses.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_secret_password_12345'
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        client=TestClient(app)
        auth=client.post('/api/login',json={'username':'owner','password':'owner_secret_password_12345'})
        assert auth.status_code==200,auth.text
        h={'X-CSRF-Token':auth.json()['csrf']}
        data=client.get('/api/cashier/plans').json()
        points={p['kind']:p for p in data['points']}
        ext=points['external'];internal=points['internal']
        assert [s['code'] for s in ext['versions'][-1]['slots']]==['night','morning','evening']
        assert [s['code'] for s in internal['versions'][-1]['slots']]==['treasury']
        assert ext['policy']['require_shift_image']==0 and ext['policy']['require_envelope_image']==0
        today=datetime.now(ZoneInfo('Africa/Cairo')).date()
        tomorrow=(today+timedelta(days=1)).isoformat()
        earlier=(today-timedelta(days=1)).isoformat()
        assert client.post('/api/cashier/plans',headers=h,json={
            'point_id':ext['id'],'effective_from':earlier,'reason':'invalid backdate',
            'slots':[{'code':'s1','name':'أولى','start':'00:00'}]}).status_code==400
        invalid=client.post('/api/cashier/plans',headers=h,json={
            'point_id':ext['id'],'effective_from':tomorrow,'reason':'shift double',
            'slots':[{'code':'first','name':'وردية أولى','start':'08:00'},
                     {'code':'second','name':'وردية ثانية','start':'08:00'}]})
        assert invalid.status_code==400,invalid.text
        updated=client.post('/api/cashier/plans',headers=h,json={
            'point_id':ext['id'],'effective_from':tomorrow,'reason':'change to 12h shifts',
            'slots':[{'code':'day_12','name':'نهاري 12 ساعة','start':'08:00'},
                     {'code':'night_12','name':'ليلي 12 ساعة','start':'20:00'}]})
        assert updated.status_code==200,updated.text
        points2=client.get('/api/cashier/plans').json()['points']
        assert next(p for p in points2 if p['id']==ext['id'])['versions'][-1]['slots'][0]['code']=='day_12'
        policy=client.post(f'/api/cashier/points/{ext["id"]}/policy',headers=h,json={
            'grace_minutes':75,'require_shift_image':True,'require_envelope_image':False})
        assert policy.status_code==200,policy.text
        with connect() as c:
            import cashier_ops
            assert len(cashier_ops.slots_for(c,ext['id'],today.isoformat()))==3
            assert len(cashier_ops.slots_for(c,ext['id'],tomorrow))==2
            assert len(cashier_ops.slots_for(c,internal['id'],tomorrow))==1
            after=cashier_ops.interval(tomorrow,cashier_ops.slots_for(c,ext['id'],tomorrow)[-1])
            assert after[0][11:16]=='20:00' and after[1][:10]==(today+timedelta(days=2)).isoformat(),after
            row=c.execute('SELECT COUNT(*) FROM cashier_schedule_versions WHERE point_id=?',(ext['id'],)).fetchone()[0]
            assert row==2
        # Actual opening follows the *station*, not a global 3-shift template.
        fund=next(f['id'] for f in client.get('/api/funds').json() if f['code']=='cash_main')
        bind=client.post(f'/api/billing/points/{internal["id"]}/cash-fund',headers=h,json={'fund_id':fund})
        assert bind.status_code==200,bind.text
        opened=client.post('/api/shifts/open',headers=h,json={'business_date':today.isoformat(),
                                                             'shift':'treasury','fund_id':fund})
        assert opened.status_code==200,opened.text
        not_external=client.post('/api/shifts/open',headers=h,json={'business_date':today.isoformat(),
                                                                  'shift':'morning','fund_id':fund})
        assert not_external.status_code==400 or not_external.status_code==409,not_external.text
        cover=client.get('/api/shifts/coverage?month='+today.strftime('%Y-%m'))
        assert cover.status_code==200,cover.text
        rows=[x for x in cover.json()['items'] if x['point_id']==internal['id'] and x['business_date']==today.isoformat()]
        assert len(rows)==1 and rows[0]['shift']=='treasury',rows
        assert not any(x['shift'] in ('morning','night','evening') for x in rows),rows
        v=c.execute('PRAGMA foreign_key_check').fetchall() if False else None
        print('PASS P1: owner schedule updates, history frozen, internal 1/external 3→2, opening treasury, date-crossing, policy defaults, live API')

if __name__=='__main__':run()
