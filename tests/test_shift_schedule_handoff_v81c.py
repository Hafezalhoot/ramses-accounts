"""V8.1C: midnight is the next day's night shift, editable windows, dual handover.

All records are test-only; the main hospital accounts and private Google Sheet are untouched.
"""
import os
import sys
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    import shift_schedule
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    conn.execute('CREATE TABLE shift_templates(code TEXT,start_minute INTEGER)')
    for code,mins in shift_schedule.DEFAULT_STARTS.items():
        conn.execute('INSERT INTO shift_templates VALUES (?,?)',(code,mins))
    for at,code,day in [
        ('2026-10-30T23:59:00+02:00','evening','2026-10-30'),
        ('2026-10-31T00:00:00+02:00','night','2026-10-31'),
        ('2026-10-31T07:59:00+02:00','night','2026-10-31'),
        ('2026-10-31T08:00:00+02:00','morning','2026-10-31'),
        ('2026-10-31T16:00:00+02:00','evening','2026-10-31'),
    ]:
        choice=shift_schedule.current_window(conn,datetime.fromisoformat(at))
        assert choice['shift']==code and choice['business_date']==day,choice
    a,b=shift_schedule.planned_interval(conn,'2026-10-31','night')
    assert a.startswith('2026-10-31T00:00') and b.startswith('2026-10-31T08:00')
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'handoff.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='temporary_strong_owner_pass_2026'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,old,new,reviewer,unassigned=(TestClient(app) for _ in range(5))
        def login(client,username,secret):
            res=client.post('/api/login',json={'username':username,'password':secret})
            assert res.status_code==200,res.text
            return {'X-CSRF-Token':res.json()['csrf']}
        oh=login(owner,'owner','temporary_strong_owner_pass_2026')
        for name,role in [('first','clerk'),('second','clerk'),('controller','reviewer'),('visitor','clerk')]:
            r=owner.post('/api/users',headers=oh,json={'username':name,'password':'staff_very_long_secret_pass_2026','role':role})
            assert r.status_code==200,r.text
        firsth=login(old,'first','staff_very_long_secret_pass_2026')
        secondh=login(new,'second','staff_very_long_secret_pass_2026')
        reviewh=login(reviewer,'controller','staff_very_long_secret_pass_2026')
        visitorh=login(unassigned,'visitor','staff_very_long_secret_pass_2026')
        sched=owner.get('/api/shifts/schedule').json()
        assert sched['windows'][0]['code']=='night' and sched['windows'][0]['start']=='00:00'
        pts=owner.get('/api/billing/config').json()['points']
        point=next(p['id'] for p in pts if p['kind']=='external')
        staff=owner.get('/api/users').json()
        ids={u['username']:u['id'] for u in staff}
        for who in ('first','second'):
            res=owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={'user_id':ids[who]})
            assert res.status_code==200,res.text
        cash=owner.post('/api/funds',headers=oh,json={'code':'handoff_cash_2026','name':'Cashier Test Drawer','kind':'cash'})
        assert cash.status_code==200,cash.text
        cashid=cash.json()['id']
        assert owner.post(f'/api/billing/points/{point}/cash-fund',headers=oh,json={'fund_id':cashid}).status_code==200
        assert owner.post(f'/api/funds/{cashid}/opening',headers=oh,json={'amount':'1000'}).status_code==200
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        s=old.post('/api/shifts/open',headers=firsth,json={'business_date':day,'shift':'night','fund_id':cashid})
        assert s.status_code==200,s.text
        sid=s.json()['id']
        configured=old.get('/api/billing/config').json()['points']
        first_point=next(p for p in configured if p['id']==point)
        assert first_point['active_shift']['shift']=='night' and first_point['own_open_shift']
        assert not next(p for p in new.get('/api/billing/config').json()['points'] if p['id']==point)['own_open_shift']
        # Cashier starts a posted receipt, reviewer approves it; shift expected = opening + cash receipt.
        look=owner.get('/api/lookups').json()
        dept=next(d['id'] for d in look['departments'] if d['code']=='LAB')
        cat=next(c['id'] for c in look['categories'] if c['code']=='medical_revenue')
        receipt=old.post('/api/vouchers',headers=firsth,json={'date':day,'kind':'receipt','shift':'night',
            'from_fund_id':cashid,'department_id':dept,'category_id':cat,
            'amount':'100','description':'Staging cash receipt for shift handover'})
        assert receipt.status_code==200,receipt.text
        approved=reviewer.post(f'/api/vouchers/{receipt.json()["id"]}/decision',headers=reviewh,
                               json={'decision':'approve'})
        assert approved.status_code==200,approved.text
        shift_report=old.get(f'/api/shifts/{sid}/daily-report')
        assert shift_report.status_code==200
        assert shift_report.json()['cash_credited_piasters']==10000
        assert shift_report.json()['expected_piasters'] is None # blind until submitted
        assert old.post(f'/api/shifts/{sid}/handoff',headers=firsth,
                        json={'counted_amount':'1100'}).status_code==409
        counted=old.post(f'/api/shifts/{sid}/count',headers=firsth,json={'counted_amount':'1100'})
        assert counted.status_code==200,counted.text
        assert new.post('/api/shifts/open',headers=secondh,json={'business_date':day,
                       'shift':'morning','fund_id':cashid}).status_code==409
        assert reviewer.post(f'/api/shifts/{sid}/review',headers=reviewh,
                             json={'decision':'approve'}).status_code==409
        assert unassigned.post(f'/api/shifts/{sid}/handoff',headers=visitorh,
                       json={'counted_amount':'1100'}).status_code==403
        received=new.get('/api/shifts?month='+day[:7]).json()['items']
        previous=next(p for p in received if p['id']==sid)
        assert previous['can_handoff'] and 'counted_piasters' not in previous
        wrong=new.post(f'/api/shifts/{sid}/handoff',headers=secondh,
                       json={'counted_amount':'1099'})
        assert wrong.status_code==409,wrong.text
        rejected=new.post(f'/api/shifts/{sid}/handoff',headers=secondh,
              json={'counted_amount':'1099','decision':'reject','note':'Independent count differs by one pound'})
        assert rejected.status_code==200 and rejected.json()['status']=='open',rejected.text
        assert old.post(f'/api/shifts/{sid}/count',headers=firsth,
              json={'counted_amount':'1100','note':'Second documented count'}).status_code==200
        ack=new.post(f'/api/shifts/{sid}/handoff',headers=secondh,
                      json={'counted_amount':'1100','note':'Independent exact physical receipt'})
        assert ack.status_code==200,ack.text
        assert new.post(f'/api/shifts/{sid}/handoff',headers=secondh,
                     json={'counted_amount':'1100'}).status_code==409
        # A good shift can roll over immediately, without waiting for accounting review.
        morning=new.post('/api/shifts/open',headers=secondh,
                         json={'business_date':day,'shift':'morning','fund_id':cashid})
        assert morning.status_code==200,morning.text
        mid=morning.json()['id']
        # Reviewer who physically accepted a till cannot also sign accounting review.
        assert reviewer.post(f'/api/shifts/{sid}/review',headers=reviewh,
                json={'decision':'approve','reason':'Verified historic postings'}).status_code==200
        # Closed yesterday's movements must stay unchanged when a new shift is open.
        prior=reviewer.get(f'/api/shifts/{sid}/movements').json()
        assert prior['expected_piasters']==110000
        s=new.post(f'/api/shifts/{mid}/count',headers=secondh,json={'counted_amount':'1100'})
        assert s.status_code==200,s.text
        assert old.post(f'/api/shifts/{mid}/handoff',headers=firsth,
              json={'counted_amount':'1100'}).status_code==200
        assert reviewer.post(f'/api/shifts/{mid}/review',headers=reviewh,
                     json={'decision':'approve'}).status_code==200
        modified=owner.post('/api/shifts/schedule',headers=oh,json={'starts':{
            'night':'01:00','morning':'09:00','evening':'17:00'},'enforce_clock':False})
        assert modified.status_code==200,modified.text
        assert modified.json()['windows'][0]['start']=='01:00'
        with connect() as conn:
            historic=conn.execute('SELECT scheduled_start_at FROM shift_sessions WHERE id=?',(sid,)).fetchone()
            assert 'T00:00' in historic['scheduled_start_at']
        assert shift_schedule.current_window(connect(),datetime.fromisoformat('2026-10-31T00:30:00+02:00'))['business_date']=='2026-10-30'
        assert shift_schedule.current_window(connect(),datetime.fromisoformat('2026-10-31T01:00:00+02:00'))['business_date']=='2026-10-31'
        print('PASS V8.1C: configurable shifts, correct night business date, blind count, independent cash receipt, rolling cash operations, separate accountant approval')


if __name__=='__main__':
    run()
