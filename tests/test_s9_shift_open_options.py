"""S9 test-first: opening options match the selected fund and business date.

All identities and accounting rows are synthetic in disposable SQLite.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s9-open-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'s9.sqlite3'),
                          RAMSES_ADMIN_USER='s9_owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_s9_owner_password_long')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import initialize, connect
        from app import app
        from fastapi.testclient import TestClient
        initialize()
        owner, clerk, outsider, viewer=[TestClient(app) for _ in range(4)]

        def ok(response,code=200):
            assert response.status_code==code,(response.status_code,code,response.text[:400])
            return response.json() if code==200 else None

        header={'X-CSRF-Token':ok(owner.post('/api/login',json={
            'username':'s9_owner','password':'synthetic_s9_owner_password_long'}))['csrf']}
        for name,role in [('s9_clerk','clerk'),('s9_outsider','clerk'),('s9_viewer','viewer')]:
            ok(owner.post('/api/users',headers=header,json={
                'username':name,'role':role,'password':'synthetic_s9_user_password_long'}))
        for client,name in [(clerk,'s9_clerk'),(outsider,'s9_outsider'),(viewer,'s9_viewer')]:
            ok(client.post('/api/login',json={
                'username':name,'password':'synthetic_s9_user_password_long'}))
        users={u['username']:u['id'] for u in ok(owner.get('/api/users'))}
        funds={x['code']:x['id'] for x in ok(owner.get('/api/funds'))}
        fund=funds['cash_sub']
        today=datetime.now(ZoneInfo('Africa/Cairo')).date()
        day=today.isoformat()
        tomorrow=(today+timedelta(days=1)).isoformat()
        old='\u0648\u0631\u062f\u064a\u0629 \u0642\u062f\u064a\u0645\u0629'
        new='\u0648\u0631\u062f\u064a\u0629 \u0645\u0633\u062a\u0642\u0628\u0644\u064a\u0629'
        point=ok(owner.post('/api/cashier/points',headers=header,json={
            'code':'S9DATEPOINT','name':'Synthetic station date-aware',
            'fund_id':fund,'reason':'Synthetic staff schedule opening regression',
            'slots':[{'code':'early','name':old,'start':'00:00'},
                     {'code':'late','name':'Late common','start':'12:00'}]
        }))['id']
        ok(owner.post('/api/cashier/plans',headers=header,json={
            'point_id':point,'effective_from':tomorrow,
            'slots':[{'code':'future','name':new,'start':'00:00'},
                     {'code':'late','name':'Late common','start':'12:00'}],
            'reason':'Synthetic future-only schedule revision'}))
        ok(owner.post(f'/api/billing/points/{point}/assign',headers=header,
                      json={'user_id':users['s9_clerk']}))
        params=lambda d,f=fund:{'fund_id':f,'business_date':d}
        with connect() as db:
            before={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                    for t in ('shift_sessions','audit_log','fund_movements','gl_journals')}
        old_options=ok(owner.get('/api/shifts/open-options',params=params(day)))
        assert [x['code'] for x in old_options['slots']]==['early','late'],old_options
        assert old_options['slots'][0]['name']==old
        assert old_options['can_open'] is True
        next_options=ok(owner.get('/api/shifts/open-options',params=params(tomorrow)))
        assert [x['code'] for x in next_options['slots']]==['future','late'],next_options
        assert next_options['slots'][0]['name']==new
        assert next_options['can_open'] is False
        assert old_options['point_id']==next_options['point_id']==point
        assert old_options['slots'][0]['name']!=next_options['slots'][0]['name']
        ok(viewer.get('/api/shifts/open-options',params=params(day)),403)
        ok(outsider.get('/api/shifts/open-options',params=params(day)),403)
        assert [x['code'] for x in ok(clerk.get('/api/shifts/open-options',params=params(day)))['slots']]==['early','late']
        ok(owner.get('/api/shifts/open-options',params={'fund_id':fund,'business_date':'not-a-date'}),400)
        ok(owner.post('/api/cashier/staff-access',headers=header,json={
            'point_id':point,'user_id':users['s9_clerk'],
            'allowed_codes':['late'],'reason':'Synthetic separate shift assignment'}))
        assert [x['code'] for x in ok(clerk.get('/api/shifts/open-options',params=params(day)))['slots']]==['late']
        assert [x['code'] for x in ok(clerk.get('/api/shifts/open-options',params=params(tomorrow)))['slots']]==['late']
        with connect() as db:
            after={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                   for t in before}
        # Only the owner staff-rights mutation wrote audit: reads did not add rows.
        assert before['shift_sessions']==after['shift_sessions']==0
        assert before['gl_journals']==after['gl_journals']
        assert before['fund_movements']==after['fund_movements']
        assert after['audit_log']==before['audit_log']+1
        # A station with an approved schedule for another weekday has no
        # selectable session today (and the write route rejects it too).
        other_fund=ok(owner.post('/api/funds',headers=header,json={
            'code':'s9_non_operating','name':'Synthetic closed weekday fund',
            'kind':'cash'}))['id']
        ok(owner.post('/api/cashier/points',headers=header,json={
            'code':'S9CLOSEDPOINT','name':'Synthetic off-day station',
            'fund_id':other_fund,'reason':'Synthetic non-operating weekday test',
            'operating_days':[(today.weekday()+1)%7],
            'slots':[{'code':'closed','name':'Off-day window','start':'08:00'}]}))
        off_day=ok(owner.get('/api/shifts/open-options',params=params(day,other_fund)))
        assert off_day['slots']==[] and off_day['can_open'] is False, off_day
        ok(owner.post('/api/shifts/open',headers=header,json={
            'business_date':day,'shift':'closed','fund_id':other_fund}),409)
        # An assigned cashier still cannot inspect a restricted till without
        # its separate cashbook grant.
        restricted_fund=ok(owner.post('/api/funds',headers=header,json={
            'code':'s9_protected','name':'Synthetic protected fund',
            'kind':'cash','restricted_cash':True}))['id']
        protected_point=ok(owner.post('/api/cashier/points',headers=header,json={
            'code':'S9PROTECTED','name':'Synthetic protected station',
            'fund_id':restricted_fund,'reason':'Synthetic protected access check',
            'slots':[{'code':'protect','name':'Protected shift','start':'00:00'}]}))['id']
        ok(owner.post(f'/api/billing/points/{protected_point}/assign',headers=header,
                      json={'user_id':users['s9_clerk']}))
        ok(clerk.get('/api/shifts/open-options',params=params(day,restricted_fund)),403)
        ok(owner.get('/api/shifts/open-options',params=params(day,restricted_fund)))
        ok(owner.post('/api/shifts/open',headers=header,json={
            'business_date':day,'shift':'future','fund_id':fund}),409)
        ok(owner.post('/api/shifts/open',headers=header,json={
            'business_date':tomorrow,'shift':'future','fund_id':fund}),400)
        old_shift=ok(owner.post('/api/shifts/open',headers=header,json={
            'business_date':day,'shift':'early','fund_id':fund}))
        assert old_shift['status']=='open'
        print('PASS S9 API: effective-dated station and shift rights, future blocked, viewer denied, no read-side financial writes')


if __name__=='__main__':
    run()
