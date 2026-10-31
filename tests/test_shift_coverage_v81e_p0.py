"""Cashier monitoring: an absent shift must be visible without inventing a financial event."""
import os
import sys
import tempfile
from datetime import datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH'] = str(Path(tmp) / 'coverage.sqlite3')
        os.environ['RAMSES_ADMIN_USER'] = 'owner_qa'
        os.environ['RAMSES_ADMIN_PASSWORD'] = 'owner_qa_password_long_2026'
        os.environ.pop('GOOGLE_SHEET_ID', None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON', None)
        from bootstrap import initialize, connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        import shift_coverage
        import shift_schedule

        owner = TestClient(app)
        clerk = TestClient(app)
        def auth(client, name, password):
            response = client.post('/api/login', json={'username': name, 'password': password})
            assert response.status_code == 200, response.text
            return {'X-CSRF-Token': response.json()['csrf']}
        oh = auth(owner, 'owner_qa', 'owner_qa_password_long_2026')
        created = owner.post('/api/users', headers=oh, json={
            'username': 'cashier_qa', 'password': 'cashier_qa_password_long_2026', 'role': 'clerk'})
        assert created.status_code == 200, created.text
        ch = auth(clerk, 'cashier_qa', 'cashier_qa_password_long_2026')
        with connect() as c:
            p = c.execute('SELECT id FROM billing_points WHERE active=1 ORDER BY id LIMIT 1').fetchone()['id']
            f = c.execute("SELECT id FROM funds WHERE kind='cash' ORDER BY id LIMIT 1").fetchone()['id']
        assigned = owner.post(f'/api/billing/points/{p}/cash-fund', headers=oh, json={'fund_id': f})
        assert assigned.status_code == 200, assigned.text
        assigned_user = owner.get('/api/users').json()
        cid = next(u['id'] for u in assigned_user if u['username'] == 'cashier_qa')
        assert owner.post(f'/api/billing/points/{p}/assign', headers=oh, json={'user_id':cid}).status_code == 200
        # Use a fully completed day: the just-ended evening shift may still be in its grace window.
        yesterday = datetime.now(ZoneInfo('Africa/Cairo')).date() - timedelta(days=2)
        with connect() as c:
            for shift, status in [('night','closed'),('morning','submitted')]:
                start, end = shift_schedule.planned_interval(c, yesterday.isoformat(), shift)
                c.execute('''INSERT INTO shift_sessions(business_date,shift,fund_id,responsible_id,
                        opened_at,opening_piasters,status,scheduled_start_at,scheduled_end_at)
                        VALUES(?,?,?,?,?,?,?,?,?)''',
                        (yesterday.isoformat(),shift,f,cid,start,0,status,start,end))
            before_count = c.execute('SELECT count(*) FROM fund_movements').fetchone()[0]
            before_sessions = c.execute('SELECT count(*) FROM shift_sessions').fetchone()[0]
        month = yesterday.strftime('%Y-%m')
        result = owner.get('/api/shifts/coverage?month=' + month)
        assert result.status_code == 200, result.text
        rows = [r for r in result.json()['items'] if r['point_id']==p and r['business_date']==yesterday.isoformat()]
        assert len(rows)==3, rows
        by_shift = {r['shift']:r for r in rows}
        assert by_shift['night']['status']=='closed', rows
        assert by_shift['morning']['status']=='awaiting_review', rows
        assert by_shift['evening']['status']=='missing', rows
        assert by_shift['evening']['session_id'] is None
        daily = [r for r in result.json()['days'] if r['point_id']==p and r['business_date']==yesterday.isoformat()]
        assert daily[0]['status']=='incomplete' and daily[0]['closed_shifts']==1
        day_response = owner.get('/api/shifts/day-summary?business_date=' + yesterday.isoformat())
        assert day_response.status_code == 200, day_response.text
        assert day_response.json()['is_provisional'] is True
        assert day_response.json()['financially_certified'] is False
        # Clerk access must never reveal unrelated points.
        restricted = clerk.get('/api/shifts/coverage?month=' + month)
        assert restricted.status_code == 200
        assert restricted.json()['items'] and all(x['point_id']==p for x in restricted.json()['items'])
        # No false alerts on days before first recorded shift.
        earlier = [r for r in result.json()['items'] if r['point_id']==p and r['business_date']<yesterday.isoformat()]
        assert all(r['status']=='not_monitored' for r in earlier), earlier
        # Early clock never marks an upcoming shift as missing.
        with connect() as c:
            fixed = datetime.combine(yesterday, time(10, 0), tzinfo=ZoneInfo('Africa/Cairo'))
            fixed_result = shift_coverage.report(c,month,{'role':'owner','id':1},at=fixed)
            later = [r for r in fixed_result['items'] if r['business_date']==yesterday.isoformat() and r['point_id']==p]
            assert {r['shift']:r['status'] for r in later}['evening']=='upcoming', later
            after_count = c.execute('SELECT count(*) FROM fund_movements').fetchone()[0]
            after_sessions = c.execute('SELECT count(*) FROM shift_sessions').fetchone()[0]
        assert (before_count,before_sessions)==(after_count,after_sessions)
        assert owner.get('/api/shifts/coverage?month=2026-13').status_code==400
        print('PASS: visible missing electronic shift, submitted review, station-day incompleteness, clerk scope, no financial mutations')


if __name__=='__main__':
    run()
