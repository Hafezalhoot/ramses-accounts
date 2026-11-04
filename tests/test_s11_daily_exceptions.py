"""Unrecorded cashier shifts must be actionable in the scoped daily report.

Synthetic SQLite only. A report read must never certify cash or write finances.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(browser_verify=None):
    with tempfile.TemporaryDirectory(prefix='ramses-s11-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='s11_owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_s11_owner_password_long')
        for key in ('GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_TARGET'):
            os.environ.pop(key, None)
        from bootstrap import initialize, connect
        from fastapi.testclient import TestClient
        from app import app
        import cashier_ops
        initialize()
        owner = TestClient(app)
        login = owner.post('/api/login', json={'username':'s11_owner',
                           'password':'synthetic_s11_owner_password_long'})
        assert login.status_code == 200, login.text
        headers = {'X-CSRF-Token':login.json()['csrf']}
        day = datetime.now(ZoneInfo('Africa/Cairo')).date()-timedelta(days=3)
        iso = day.isoformat()
        with connect() as c:
            points = [dict(r) for r in c.execute('SELECT id FROM billing_points ORDER BY id LIMIT 2')]
            funds = [r['id'] for r in c.execute("SELECT id FROM funds WHERE kind='cash' ORDER BY id LIMIT 2")]
        for point, fund in zip(points, funds):
            r = owner.post(f"/api/billing/points/{point['id']}/cash-fund", headers=headers,
                           json={'fund_id':fund})
            assert r.status_code == 200, r.text
        with connect() as c:
            start = (day-timedelta(days=14)).isoformat()
            c.execute('UPDATE cashier_schedule_versions SET starts_on=?', (start,))
            c.execute('UPDATE cashier_point_lifecycle SET starts_on=?', (start,))
            c.execute('UPDATE cashier_schedule_versions SET operating_days=?', ('0123456',))
            uid = c.execute("SELECT id FROM users WHERE username='s11_owner'").fetchone()['id']
            slots = cashier_ops.slots_for(c, points[0]['id'], iso)
            assert len(slots) == 3, slots
            # One closed, one awaiting review and one never registered.
            for slot, status in zip(slots[:2], ('closed', 'submitted')):
                begin, end = cashier_ops.interval(iso, slot)
                c.execute('''INSERT INTO shift_sessions(business_date,shift,point_id,fund_id,
                    responsible_id,opened_at,opening_piasters,status,scheduled_start_at,scheduled_end_at)
                    VALUES (?,?,?,?,?,?,0,?,?,?)''',
                    (iso,slot['code'],points[0]['id'],funds[0],uid,begin,status,begin,end))
            # The second point is private to explicitly granted reviewers.
            c.execute('UPDATE funds SET cash_restricted=1 WHERE id=?', (funds[1],))
        created = owner.post('/api/users', headers=headers, json={'username':'s11_reviewer',
                             'role':'reviewer','password':'synthetic_s11_staff_password_long'})
        assert created.status_code == 200, created.text
        reviewer = TestClient(app)
        assert reviewer.post('/api/login', json={'username':'s11_reviewer',
                    'password':'synthetic_s11_staff_password_long'}).status_code == 200
        tables = ('gl_journals','fund_movements','audit_log','shift_sessions','vouchers')
        with connect() as c:
            before = {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables}
        def report(client, date=iso):
            r = client.get('/api/shifts/day-summary', params={'business_date':date})
            assert r.status_code == 200, r.text
            return r.json()
        result = report(owner)
        assert result['is_provisional'] and not result['financially_certified']
        exceptions = result['coverage_exceptions']
        assert len(exceptions) == 3, exceptions  # 2 external + 1 private treasury slot
        own = [e for e in exceptions if e['point_id'] == points[0]['id']]
        assert sorted(e['status'] for e in own) == ['awaiting_review','missing'], own
        assert all(e['shift_name'] and e['business_date']==iso for e in own)
        assert next(e for e in own if e['status']=='missing')['session_id'] is None
        scoped = report(reviewer)
        assert len(scoped['coverage_exceptions']) == 2, scoped
        assert all(e['point_id']==points[0]['id'] for e in scoped['coverage_exceptions'])
        # No schedule history must be visible as unknown, never zero activity.
        unknown = report(owner, (day-timedelta(days=15)).isoformat())
        assert len(unknown['coverage_exceptions']) == 2, unknown
        assert {e['status'] for e in unknown['coverage_exceptions']} == {'not_monitored'}
        assert unknown['is_provisional'] and not unknown['financially_certified']
        # Upcoming work remains upcoming, never described as overdue/missing.
        future = report(owner, (day+timedelta(days=10)).isoformat())
        assert {e['status'] for e in future['coverage_exceptions']} == {'upcoming'}
        assert future['is_provisional'] and not future['financially_certified']
        assert TestClient(app).get('/api/shifts/day-summary', params={'business_date':iso}).status_code == 401
        with connect() as c:
            assert before == {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables}
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        if browser_verify:
            browser_verify(app, iso, result, connect)
        print('PASS S11 daily exceptions: missing/review/unknown/upcoming, scoped report, no certification or writes')


if __name__ == '__main__':
    run()
