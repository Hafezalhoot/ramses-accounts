"""S2: same physical treasury deposit must post exactly once on request retry."""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(browser_verify=None):
    with tempfile.TemporaryDirectory(prefix='ramses-s2-retry-') as temp:
        os.environ.update(RAMSES_DB_PATH=str(Path(temp) / 'retry.sqlite3'),
                          RAMSES_ADMIN_USER='owner', RAMSES_ADMIN_PASSWORD='synthetic_s2_owner_retry_secret')
        for key in ('GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_ID', 'GOOGLE_SHEET_TARGET'):
            os.environ.pop(key, None)
        from bootstrap import initialize, connect
        from app import app
        from fastapi.testclient import TestClient
        initialize()
        sessions = {u: TestClient(app) for u in ('owner', 'clerk', 'receiver', 'reviewer')}
        def check(resp, status=200):
            assert resp.status_code == status, (status, resp.status_code, resp.text[:500])
            return resp.json() if status == 200 else None
        auth = {'owner': {'X-CSRF-Token': check(sessions['owner'].post('/api/login', json={
            'username': 'owner', 'password': 'synthetic_s2_owner_retry_secret'}))['csrf']}}
        for name in ('clerk', 'receiver', 'reviewer'):
            check(sessions['owner'].post('/api/users', headers=auth['owner'], json={
                'username': name, 'password': 'synthetic_s2_retry_staff_password',
                'role': 'reviewer' if name == 'reviewer' else 'clerk'}))
            auth[name] = {'X-CSRF-Token': check(sessions[name].post('/api/login', json={
                'username': name, 'password': 'synthetic_s2_retry_staff_password'}))['csrf']}
        users = {u['username']: u['id'] for u in check(sessions['owner'].get('/api/users'))}
        points = check(sessions['owner'].get('/api/cashier/plans'))['points']
        ext = next(p for p in points if p['kind'] == 'external')
        central = next(p for p in points if p['kind'] == 'internal')
        funds = {f['code']: f['id'] for f in check(sessions['owner'].get('/api/funds'))}
        for p, fid in ((ext, funds['cash_sub']), (central, funds['cash_main'])):
            check(sessions['owner'].post(f'/api/billing/points/{p["id"]}/cash-fund',
                                         headers=auth['owner'], json={'fund_id': fid}))
        for person, point in (('clerk', ext), ('receiver', ext), ('receiver', central)):
            check(sessions['owner'].post(f'/api/billing/points/{point["id"]}/assign',
                                         headers=auth['owner'], json={'user_id': users[person]}))
        day = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        source = check(sessions['clerk'].post('/api/shifts/open', headers=auth['clerk'], json={
            'business_date': day, 'shift': 'night', 'fund_id': funds['cash_sub']}))['id']
        target = check(sessions['receiver'].post('/api/shifts/open', headers=auth['receiver'], json={
            'business_date': day, 'shift': 'treasury', 'fund_id': funds['cash_main']}))['id']
        lookups = check(sessions['owner'].get('/api/lookups'))
        dept = next(x['id'] for x in lookups['departments'] if x['code'] == 'CLINIC')
        category = next(x['id'] for x in lookups['categories'] if x['code'] == 'medical_revenue')
        voucher = check(sessions['clerk'].post('/api/vouchers', headers=auth['clerk'], json={
            'date': day, 'kind': 'receipt', 'shift': 'night', 'from_fund_id': funds['cash_sub'],
            'department_id': dept, 'category_id': category, 'amount': '200',
            'description': 'S2 synthetic retry test collection'}))['id']
        check(sessions['reviewer'].post(f'/api/vouchers/{voucher}/decision',
                                        headers=auth['reviewer'], json={'decision': 'approve'}))
        check(sessions['clerk'].post(f'/api/shifts/{source}/count',
                                     headers=auth['clerk'], json={'counted_amount': '200'}))
        check(sessions['receiver'].post(f'/api/shifts/{source}/handoff',
                                        headers=auth['receiver'], json={'counted_amount': '200', 'decision': 'accept'}))
        visible = check(sessions['receiver'].get('/api/shifts', params={'month': day[:7]}))['items']
        eligible = next(x for x in visible if x['id'] == source)
        assert eligible['can_treasury_deposit'] is True and eligible['treasury_remaining_piasters'] == 20000, eligible
        unauthorized = check(sessions['clerk'].get('/api/shifts', params={'month': day[:7]}))['items']
        assert not next(x for x in unauthorized if x['id'] == source)['can_treasury_deposit']
        deposit = {'source_shift_id': source, 'amount': '50', 'note': 'S2 synthetic sealed envelope 50',
                   'client_request_id': 's2-test-deposit-idempotent-001'}
        first = check(sessions['receiver'].post('/api/cashier/treasury-deposits',
                                               headers=auth['receiver'], json=deposit))
        second = check(sessions['receiver'].post('/api/cashier/treasury-deposits',
                                                headers=auth['receiver'], json=deposit))
        assert second['voucher_id'] == first['voucher_id'] and second.get('replayed') is True, (first, second)
        check(sessions['receiver'].post('/api/cashier/treasury-deposits', headers=auth['receiver'],
                                        json={**deposit, 'amount': '60'}), 409)
        # Losing the request key must not book the same physical reference twice.
        check(sessions['receiver'].post('/api/cashier/treasury-deposits', headers=auth['receiver'],
                                        json={**deposit, 'client_request_id': 's2-other-device-request-001'}), 409)
        check(sessions['clerk'].post('/api/cashier/treasury-deposits', headers=auth['clerk'],
                                     json=deposit), 409)
        # Closing accounting review must not strand the remaining physical cash:
        # the actual independent receiver may still transfer it before a later till shift.
        check(sessions['reviewer'].post(f'/api/shifts/{source}/review',
                                        headers=auth['reviewer'], json={'decision': 'approve'}))
        closed = check(sessions['receiver'].get('/api/shifts', params={'month': day[:7]}))['items']
        closed_source = next(x for x in closed if x['id'] == source)
        assert closed_source['status'] == 'closed' and closed_source['can_treasury_deposit'], closed_source
        if browser_verify:
            browser_verify(app, source, connect)
        # A simultaneous network retry cannot create two vouchers or two GL journals.
        from concurrent.futures import ThreadPoolExecutor
        concurrent = {**deposit, 'amount': '15',
                      'note': 'S2 independent additional cash envelope',
                      'client_request_id': 's2-test-concurrent-deposit-002'}
        def submit(_):
            return check(sessions['receiver'].post('/api/cashier/treasury-deposits',
                    headers=auth['receiver'], json=concurrent))
        with ThreadPoolExecutor(max_workers=2) as pool:
            pair = list(pool.map(submit, range(2)))
        assert pair[0]['voucher_id'] == pair[1]['voucher_id'], pair
        assert sum(bool(r.get('replayed')) for r in pair) == 1, pair
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM cashier_treasury_transfers').fetchone()[0] == (4 if browser_verify else 2)
            assert c.execute('SELECT COUNT(*) FROM fund_movements WHERE voucher_id=?',
                             (first['voucher_id'],)).fetchone()[0] == 2
            assert c.execute('SELECT COUNT(*) FROM gl_journals WHERE source_id=? AND origin=?',
                             (first['voucher_id'], 'voucher')).fetchone()[0] == 1
            assert c.execute('SELECT SUM(amount_piasters) FROM cashier_treasury_transfers').fetchone()[0] == (11500 if browser_verify else 6500)
            assert c.execute('SELECT COUNT(*) FROM voucher_request_keys WHERE voucher_id=?',
                             (first['voucher_id'],)).fetchone()[0] == 1
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        print('PASS S2: partial retry and concurrent replay return one voucher; mismatch rejected; movement/GL balanced')


if __name__ == '__main__':
    run()
