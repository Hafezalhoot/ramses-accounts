"""Seed a FRESH preview SQLite database through the same app API as real users.

All names, amounts and references are fabricated. Never run against another DB.
"""
import os
import secrets
from datetime import date
from pathlib import Path


def seed_demo(root: Path, admin_password: str) -> dict:
    if os.getenv('RAMSES_ENVIRONMENT') != 'free-preview':
        raise RuntimeError('Demo seeding is allowed only in free-preview mode')
    db_file = Path(os.environ['RAMSES_DB_PATH']).resolve()
    expected = (root / 'data' / 'free-preview.sqlite3').resolve()
    if db_file != expected:
        raise RuntimeError('Refusing to seed a database other than the isolated preview DB')
    from bootstrap import connect
    conn = connect()
    try:
        if (conn.execute('SELECT COUNT(*) FROM vouchers').fetchone()[0] or
                conn.execute("SELECT COUNT(*) FROM users WHERE username='preview_reviewer'").fetchone()[0]):
            return {'skipped': 'Sample data already exists'}
    finally:
        conn.close()

    # Disable any remote mirror during seeding; user can manually sync the test snapshot later.
    old_sheet = os.environ.pop('GOOGLE_SHEET_ID', None)
    old_key = os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON', None)
    try:
        from app import app
        from fastapi.testclient import TestClient
        maker = TestClient(app)
        checker = TestClient(app)
        who = os.getenv('RAMSES_ADMIN_USER', 'owner')
        resp = maker.post('/api/login', json={'username': who, 'password': admin_password})
        if resp.status_code != 200:
            raise RuntimeError(f'Could not initialize demo owner session: {resp.status_code}')
        mh = {'X-CSRF-Token': resp.json()['csrf']}
        pw = secrets.token_urlsafe(24)
        resp = maker.post('/api/users', json={'username': 'preview_reviewer',
                                              'password': pw, 'role': 'reviewer'}, headers=mh)
        if resp.status_code != 200:
            raise RuntimeError('Cannot create isolated demo reviewer account: ' + resp.text[:160])
        reviewer_id = resp.json()['id']
        resp = checker.post('/api/login', json={'username': 'preview_reviewer', 'password': pw})
        assert resp.status_code == 200
        rh = {'X-CSRF-Token': resp.json()['csrf']}
        look = maker.get('/api/lookups').json()
        fund_id = next(f['id'] for f in look['funds'] if f['code'] == 'cash_main')
        wallet_id = next(f['id'] for f in look['funds'] if f['code'] == 'vodafone')
        # Demo wallet approval follows the same explicit grant rules as normal users.
        grant = maker.post('/api/fund-access', json={
            'user_id': reviewer_id, 'fund_id': wallet_id,
            'can_approve': True, 'reason': 'Sample-only wallet voucher approval'}, headers=mh)
        if grant.status_code != 200:
            raise RuntimeError('Cannot grant demo reviewer wallet approval: '+grant.text[:160])
        dept_id = next(d['id'] for d in look['departments'] if d['code'] == 'ER')
        revenue = next(k['id'] for k in look['categories'] if k['code'] == 'medical_revenue')
        expenses = next(k['id'] for k in look['categories'] if k['code'] == 'utilities')
        resp = maker.post(f'/api/funds/{fund_id}/opening', json={'amount':'3000.00'}, headers=mh)
        assert resp.status_code == 200, resp.text
        today = date.today().isoformat()
        examples = [
            ('receipt', revenue, '1250.00', None, 'عملية اختبار إيراد وهمية'),
            ('payment', expenses, '185.50', None, 'عملية اختبار مصروف مرافق وهمية'),
            ('transfer', None, '400.00', wallet_id, 'تحويل تجريبي لمحفظة وهمية'),
        ]
        for kind, category, amount, destination, memo in examples:
            payload = {'date':today, 'kind':kind, 'department_id':dept_id,
                       'category_id':category, 'from_fund_id':fund_id,
                       'to_fund_id':destination, 'shift':'central',
                       'amount':amount, 'description':memo,
                       'reference_no':'DEMO-ONLY'}
            response = maker.post('/api/vouchers', json=payload, headers=mh)
            if response.status_code != 200:
                raise RuntimeError(f'Demo voucher rejected: {response.text[:150]}')
            decision = checker.post(f'/api/vouchers/{response.json()["id"]}/decision',
                                    json={'decision':'approve'}, headers=rh)
            if decision.status_code != 200:
                raise RuntimeError(f'Demo voucher approval rejected: {decision.text[:150]}')
        maker.post('/api/logout', headers=mh)
        checker.post('/api/logout', headers=rh)
        return {'seeded':3, 'reviewer_username':'preview_reviewer', 'reviewer_password':pw}
    finally:
        if old_sheet is not None:os.environ['GOOGLE_SHEET_ID'] = old_sheet
        if old_key is not None:os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'] = old_key
