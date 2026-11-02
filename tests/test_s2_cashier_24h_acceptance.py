"""S2: night/morning/evening cashier -> internal treasury -> GL, synthetic SQLite only."""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s2-24h-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder) / 'day.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_s2_owner_long_secret')
        for key in ('GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_ID', 'GOOGLE_SHEET_TARGET'):
            os.environ.pop(key, None)
        from bootstrap import initialize, connect
        from app import app
        from fastapi.testclient import TestClient
        initialize()
        names = ('owner', 'night', 'morning', 'evening', 'treasury', 'reviewer')
        clients = {name: TestClient(app) for name in names}

        def ok(response, status=200):
            assert response.status_code == status, (response.status_code, response.text[:500])
            return response.json() if status == 200 else None

        owner = clients['owner']
        passwords = {'owner': 'synthetic_s2_owner_long_secret'}
        headers = {'owner': {'X-CSRF-Token': ok(owner.post('/api/login', json={
            'username': 'owner', 'password': passwords['owner']}))['csrf']}}
        for name in names[1:]:
            passwords[name] = 'synthetic_s2_staff_long_password'
            ok(owner.post('/api/users', headers=headers['owner'], json={
                'username': name, 'password': passwords[name],
                'role': 'reviewer' if name == 'reviewer' else 'clerk'}))
            headers[name] = {'X-CSRF-Token': ok(clients[name].post('/api/login', json={
                'username': name, 'password': passwords[name]}))['csrf']}
        ids = {u['username']: u['id'] for u in ok(owner.get('/api/users'))}
        pts = ok(owner.get('/api/cashier/plans'))['points']
        external = next(p for p in pts if p['kind'] == 'external')
        internal = next(p for p in pts if p['kind'] == 'internal')
        funds = {f['code']: f['id'] for f in ok(owner.get('/api/funds'))}
        sub, main = funds['cash_sub'], funds['cash_main']
        for point, fund in ((external, sub), (internal, main)):
            ok(owner.post(f'/api/billing/points/{point["id"]}/cash-fund',
                          headers=headers['owner'], json={'fund_id': fund}))
        for name in ('night', 'morning', 'evening', 'treasury'):
            ok(owner.post(f'/api/billing/points/{external["id"]}/assign',
                          headers=headers['owner'], json={'user_id': ids[name]}))
        ok(owner.post(f'/api/billing/points/{internal["id"]}/assign',
                      headers=headers['owner'], json={'user_id': ids['treasury']}))
        day = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        central = clients['treasury']
        central_id = ok(central.post('/api/shifts/open', headers=headers['treasury'],
                          json={'business_date': day, 'shift': 'treasury', 'fund_id': main}))['id']
        look = ok(owner.get('/api/lookups'))
        dept = next(x['id'] for x in look['departments'] if x['code'] == 'CLINIC')
        admin = next(x['id'] for x in look['departments'] if x['code'] == 'ADMIN')
        income = next(x['id'] for x in look['categories'] if x['code'] == 'medical_revenue')
        utilities = next(x['id'] for x in look['categories'] if x['code'] == 'utilities')
        shifts = []
        for name, amount in (('night', 100), ('morning', 200), ('evening', 300)):
            worker = clients[name]
            sid = ok(worker.post('/api/shifts/open', headers=headers[name], json={
                'business_date': day, 'shift': name, 'fund_id': sub}))['id']
            shifts.append(sid)
            invoice = ok(worker.post('/api/vouchers', headers=headers[name], json={
                'date': day, 'kind': 'receipt', 'shift': name, 'from_fund_id': sub,
                'department_id': dept, 'category_id': income, 'amount': str(amount),
                'description': 'Synthetic hospital shift collection'}))['id']
            ok(clients['reviewer'].post(f'/api/vouchers/{invoice}/decision',
                                       headers=headers['reviewer'], json={'decision': 'approve'}))
            ok(worker.post(f'/api/shifts/{sid}/count', headers=headers[name],
                           json={'counted_amount': str(amount), 'note': 'S2 counted test drawer'}))
            # Nobody can hand themselves a drawer; central receiver is distinct from the cashier.
            ok(worker.post(f'/api/shifts/{sid}/handoff', headers=headers[name],
                           json={'counted_amount': str(amount)}), 403)
            ok(central.post(f'/api/shifts/{sid}/handoff', headers=headers['treasury'],
                            json={'counted_amount': str(amount), 'decision': 'accept',
                                  'note': 'S2 independently counted handover'}))
            ok(worker.post('/api/cashier/treasury-deposits', headers=headers[name], json={
                'source_shift_id': sid, 'amount': str(amount),
                'note': 'S2 attempted deposit by wrong cashier'}), 403)
            deposit = ok(central.post('/api/cashier/treasury-deposits', headers=headers['treasury'], json={
                'source_shift_id': sid, 'amount': str(amount),
                'note': f'S2 physical deposit {name} to central treasury'}))
            assert deposit['amount_piasters'] == amount * 100
            ok(central.post('/api/cashier/treasury-deposits', headers=headers['treasury'], json={
                'source_shift_id': sid, 'amount': str(amount),
                'note': f'S2 repeated completed deposit {name}'}), 409)
            ok(clients['reviewer'].post(f'/api/shifts/{sid}/review', headers=headers['reviewer'],
                                        json={'decision': 'approve'}))
        expense = ok(central.post('/api/vouchers', headers=headers['treasury'], json={
            'date': day, 'kind': 'payment', 'shift': 'central', 'from_fund_id': main,
            'department_id': admin, 'category_id': utilities, 'amount': '50',
            'description': 'S2 synthetic internal hospital running expense'}))['id']
        ok(clients['reviewer'].post(f'/api/vouchers/{expense}/decision',
                                    headers=headers['reviewer'], json={'decision': 'approve'}))
        count = ok(central.post(f'/api/shifts/{central_id}/count', headers=headers['treasury'],
                                json={'counted_amount': '550', 'note': 'S2 central close'}))
        assert count['variance_piasters'] == 0
        ok(owner.post(f'/api/shifts/{central_id}/handoff', headers=headers['owner'],
                      json={'counted_amount': '550', 'decision': 'accept', 'note': 'S2 independent central receipt'}))
        ok(clients['reviewer'].post(f'/api/shifts/{central_id}/review', headers=headers['reviewer'],
                                    json={'decision': 'approve'}))
        summary = ok(owner.get('/api/shifts/day-summary', params={'business_date': day}))
        assert len(summary['stations']) == 4, summary
        assert {s['status'] for s in summary['stations']} == {'closed'}, summary
        assert summary['pending_accounting_review'] == 0
        assert summary['shift_coverage_complete'] is True, summary['coverage']
        with connect() as c:
            fund_balance = lambda fid: c.execute('''SELECT opening_piasters + COALESCE(
                 (SELECT SUM(amount_piasters) FROM fund_movements WHERE fund_id=?),0)
                 FROM funds WHERE id=?''', (fid, fid)).fetchone()[0]
            assert fund_balance(sub) == 0
            assert fund_balance(main) == 55000
            assert c.execute('SELECT COUNT(*) FROM cashier_treasury_transfers').fetchone()[0] == 3
            actual = {r['code']: (r['dr'], r['cr']) for r in c.execute('''
                SELECT a.code, SUM(l.debit_piasters) dr,SUM(l.credit_piasters) cr
                FROM gl_lines l JOIN gl_accounts a ON a.id=l.account_id
                JOIN gl_journals j ON j.id=l.journal_id
                WHERE j.status='posted' GROUP BY a.code''')}
            assert actual['4100'][1] == 60000, actual
            assert actual['5140'][0] == 5000, actual
            assert sum(r[0] for r in actual.values()) == sum(r[1] for r in actual.values())
            assert c.execute("SELECT COUNT(*) FROM shift_sessions WHERE status='closed'").fetchone()[0] == 4
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS S2: 3 external + 1 internal shifts, 600 EGP cash -> main, 50 EGP expense, 550 EGP cash, 4 independently closed, GL balanced')


if __name__ == '__main__':
    run()
