"""S10: non-working cashier points must not falsify a complete cash day.

No production data, postings or hospital infrastructure. The read-only
report must distinguish a scheduled absence from an operational off-day.
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
    with tempfile.TemporaryDirectory(prefix='ramses-s10-day-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='s10_owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_s10_owner_password_long')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import initialize, connect
        from fastapi.testclient import TestClient
        from app import app
        import cashier_ops
        initialize()
        owner=TestClient(app)
        logged=owner.post('/api/login',json={
            'username':'s10_owner','password':'synthetic_s10_owner_password_long'})
        assert logged.status_code==200,logged.text
        # The shipped baseline has deliberately unbound points; attach two
        # disposable test cash drawers using the same owner route as operation.
        with connect() as c:
            seeded_points=[r['id'] for r in c.execute('SELECT id FROM billing_points ORDER BY id')]
            seeded_funds=[r['id'] for r in c.execute("SELECT id FROM funds WHERE kind='cash' ORDER BY id")]
        assert len(seeded_points)>=2 and len(seeded_funds)>=2
        for point_id, fund_id in zip(seeded_points[:2],seeded_funds[:2]):
            assigned=owner.post(f'/api/billing/points/{point_id}/cash-fund',
                                headers={'X-CSRF-Token':logged.json()['csrf']},
                                json={'fund_id':fund_id})
            assert assigned.status_code==200,assigned.text
        day=(datetime.now(ZoneInfo('Africa/Cairo')).date()-timedelta(days=3))
        iso=day.isoformat()
        with connect() as c:
            uid=c.execute("SELECT id FROM users WHERE username='s10_owner'").fetchone()['id']
            points=[dict(p) for p in c.execute('''SELECT p.id,p.fund_id,p.kind
               FROM billing_points p WHERE p.fund_id IS NOT NULL
               AND EXISTS (SELECT 1 FROM cashier_schedule_versions v WHERE v.point_id=p.id)
               ORDER BY p.id''')]
            assert len(points)>=2,points
            active=next((p for p in points if p['kind']=='external'),points[0])
            # Move only the disposable seed schedules/lifecycle before this day.
            start=(day-timedelta(days=14)).isoformat()
            c.execute('UPDATE cashier_schedule_versions SET starts_on=? WHERE starts_on>?',
                      (start,start))
            c.execute('UPDATE cashier_point_lifecycle SET starts_on=? WHERE starts_on>?',
                      (start,start))
            for p in points:
                v=cashier_ops.version_for(c,p['id'],iso)
                assert v is not None,p
                # One operating weekday per station, staggered deliberately:
                # target day has one required station and one approved day off.
                active_weekday=day.weekday()
                operating=active_weekday if p['id']==active['id'] else (active_weekday+1)%7
                c.execute('UPDATE cashier_schedule_versions SET operating_days=? WHERE id=?',
                          (str(operating),v['id']))
            slots=cashier_ops.slots_for(c,active['id'],iso)
            assert slots and len(slots)>0,slots
            for slot in slots:
                start,end=cashier_ops.interval(iso,slot)
                c.execute('''INSERT INTO shift_sessions(business_date,shift,point_id,fund_id,
                   responsible_id,opened_at,opening_piasters,status,scheduled_start_at,scheduled_end_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)''',
                   (iso,slot['code'],active['id'],active['fund_id'],uid,start,0,'closed',start,end))
            before={tbl:c.execute('SELECT COUNT(*) FROM '+tbl).fetchone()[0]
                    for tbl in ('gl_journals','fund_movements','audit_log','shift_sessions')}
        cov=owner.get('/api/shifts/coverage',params={'month':iso[:7]})
        assert cov.status_code==200,cov.text
        daily=[x for x in cov.json()['days'] if x['business_date']==iso]
        assert next(x for x in daily if x['point_id']==active['id'])['status']=='complete',daily
        assert any(x['status']=='not_required' for x in daily),daily
        assert not any(x['status'] in ('incomplete','in_progress') for x in daily),daily
        response=owner.get('/api/shifts/day-summary',params={'business_date':iso})
        assert response.status_code==200,response.text
        result=response.json()
        assert result['shift_coverage_complete'] is True,result['coverage']
        assert result['is_provisional'] is False,result
        assert result['financially_certified'] is False,result
        # A different date with required cashier shifts and no closures remains provisional.
        missing_iso=(day-timedelta(days=7)).isoformat()
        missing=owner.get('/api/shifts/day-summary',params={'business_date':missing_iso})
        assert missing.status_code==200,missing.text
        assert missing.json()['shift_coverage_complete'] is False,missing.json()['coverage']
        assert missing.json()['is_provisional'] is True
        assert any(x['status']=='incomplete' for x in missing.json()['coverage'])
        # No station is required two weekdays later; 'nothing scheduled' does
        # not certify any real cashier activity or a complete financial day.
        empty_iso=(day+timedelta(days=2)).isoformat()
        empty=owner.get('/api/shifts/day-summary',params={'business_date':empty_iso})
        assert empty.status_code==200,empty.text
        assert all(x['status']=='not_required' for x in empty.json()['coverage']),empty.json()['coverage']
        assert empty.json()['shift_coverage_complete'] is False
        # Before the first configured schedule, monitoring is unknown, not complete.
        unknown_iso=(day-timedelta(days=15)).isoformat()
        unknown=owner.get('/api/shifts/day-summary',params={'business_date':unknown_iso})
        assert unknown.status_code==200,unknown.text
        assert unknown.json()['shift_coverage_complete'] is False
        assert unknown.json()['is_provisional'] is True
        denied=owner.get('/api/shifts/day-summary',params={'business_date':'not-a-date'})
        assert denied.status_code==400,denied.text
        no_session=TestClient(app).get('/api/shifts/day-summary',params={'business_date':iso})
        assert no_session.status_code==401,no_session.text
        with connect() as c:
            after={tbl:c.execute('SELECT COUNT(*) FROM '+tbl).fetchone()[0] for tbl in before}
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert before==after,(before,after)
        print('PASS S10: off-day neutral, all required shifts closed, missing remains provisional, HTTP auth, no financial writes')


if __name__=='__main__':
    run()
