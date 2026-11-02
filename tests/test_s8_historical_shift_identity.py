"""S8: an effective-dated cashier name must not be rewritten by tomorrow's plan.

All data is artificial, with actual API/auth/SQLite and no money movements.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s8-history-') as temp:
        os.environ.update(RAMSES_DB_PATH=str(Path(temp) / 's8.sqlite3'),
                          RAMSES_ADMIN_USER='s8_owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_s8_owner_password_long')
        for key in ('GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_TARGET'):
            os.environ.pop(key, None)
        from bootstrap import initialize, connect
        from app import app
        from fastapi.testclient import TestClient
        initialize()
        owner = TestClient(app)
        viewer = TestClient(app)

        def ok(response, status=200):
            assert response.status_code == status, (response.status_code, response.text[:500])
            return response.json() if status == 200 else None

        owner_header = {'X-CSRF-Token': ok(owner.post('/api/login', json={
            'username': 's8_owner', 'password': 'synthetic_s8_owner_password_long'}))['csrf']}
        ok(owner.post('/api/users', headers=owner_header, json={
            'username':'s8_viewer', 'role':'viewer', 'password':'synthetic_s8_viewer_password'}))
        ok(viewer.post('/api/login', json={'username':'s8_viewer',
                                          'password':'synthetic_s8_viewer_password'}))
        funds = {r['code']:r['id'] for r in ok(owner.get('/api/funds'))}
        fund_id = funds['cash_sub']
        day = datetime.now(ZoneInfo('Africa/Cairo')).date()
        today, tomorrow = day.isoformat(), (day + timedelta(days=1)).isoformat()
        old_name = 'وردية استقبال قديمة ثابتة'
        future_name = 'وردية ستتغير غداً فقط'
        point = ok(owner.post('/api/cashier/points', headers=owner_header, json={
            'code':'S8HISTORY', 'name':'نقطة اختبار الوردية التاريخية',
            'fund_id':fund_id, 'reason':'Synthetic historical shift identity QA',
            'slots':[{'code':'desk','name':old_name,'start':'00:00'}]
        }))['id']
        shift_id = ok(owner.post('/api/shifts/open', headers=owner_header, json={
            'business_date':today, 'shift':'desk', 'fund_id':fund_id}))['id']
        ok(owner.post('/api/cashier/plans', headers=owner_header, json={
            'point_id':point, 'effective_from':tomorrow,
            'slots':[{'code':'desk','name':future_name,'start':'00:00'}],
            'reason':'Synthetic future rename, historical names stay intact'}))
        with connect() as c:
            before = [c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                      for table in ('fund_movements', 'gl_journals', 'audit_log', 'shift_sessions')]
        shifts = ok(owner.get('/api/shifts', params={'month':today[:7]}))['items']
        historical = next(x for x in shifts if x['id']==shift_id)
        assert historical['point_id']==point and historical['shift']=='desk', historical
        assert historical.get('shift_name')==old_name, ('list lost historical label', historical)
        daily = ok(owner.get(f'/api/shifts/{shift_id}/daily-report'))
        assert daily['shift']=='desk' and daily.get('shift_name')==old_name, daily
        summary = ok(owner.get('/api/shifts/day-summary', params={'business_date':today}))
        day_row = next(x for x in summary['stations'] if x['id']==shift_id)
        assert day_row['shift']=='desk' and day_row.get('shift_name')==old_name, day_row
        assert future_name not in str(day_row), day_row
        assert summary['financially_certified'] is False
        ok(viewer.get('/api/shifts/day-summary', params={'business_date':today}), 403)
        with connect() as c:
            after = [c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                     for table in ('fund_movements', 'gl_journals', 'audit_log', 'shift_sessions')]
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        assert before==after, ('Read-only reports must not write to finance or audit',before,after)
        print('PASS S8 API: original effective-dated label in list/day report, viewer denied, zero ledger or audit writes')


if __name__=='__main__':
    run()
