"""G2Y: report aggregates must not reconstruct protected fund totals.

API integration test against a disposable SQLite database with synthetic money.
The intentional mutation: remove `voucher_visible_sql()` from report SQL and
this test must fail without trusting any UI hiding behavior.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ.update(
            RAMSES_DB_PATH=str(Path(td) / 'reports.sqlite3'),
            RAMSES_ADMIN_USER='owner',
            RAMSES_ADMIN_PASSWORD='synthetic_owner_report_scope_password',
        )
        from bootstrap import connect, initialize
        initialize()
        from app import app
        from fastapi.testclient import TestClient

        owner, reviewer, viewer, anonymous = (TestClient(app) for _ in range(4))

        def ok(response, code=200):
            assert response.status_code == code, (code, response.status_code, response.text[:400])
            return response.json() if code == 200 else None

        def login(client, name, password):
            return {'X-CSRF-Token': ok(client.post('/api/login', json={
                'username': name, 'password': password}))['csrf']}

        owner_headers = login(owner, 'owner', 'synthetic_owner_report_scope_password')
        reviewer_id = ok(owner.post('/api/users', headers=owner_headers, json={
            'username': 'report_reviewer', 'role': 'reviewer',
            'password': 'synthetic_report_reviewer_password'}))['id']
        ok(owner.post('/api/users', headers=owner_headers, json={
            'username': 'report_viewer', 'role': 'viewer',
            'password': 'synthetic_report_viewer_password'}))
        login(reviewer, 'report_reviewer', 'synthetic_report_reviewer_password')
        login(viewer, 'report_viewer', 'synthetic_report_viewer_password')

        normal = ok(owner.post('/api/funds', headers=owner_headers, json={
            'code': 'REPORT_OPEN', 'name': 'Unrestricted sample cash', 'kind': 'cash'}))['id']
        bank = ok(owner.post('/api/funds', headers=owner_headers, json={
            'code': 'REPORT_BANK', 'name': 'Private sample bank', 'kind': 'bank'}))['id']
        restricted = ok(owner.post('/api/funds', headers=owner_headers, json={
            'code': 'REPORT_PRIVATE', 'name': 'Private sample cash', 'kind': 'cash',
            'restricted_cash': True}))['id']
        with connect() as c:
            owner_id = c.execute("SELECT id FROM users WHERE username='owner'").fetchone()[0]
            dept_id = c.execute("SELECT id FROM departments WHERE code='ADMIN'").fetchone()[0]
            category = c.execute("SELECT id FROM categories WHERE code='other_revenue'").fetchone()[0]
            payment_category = c.execute("SELECT id FROM categories WHERE nature='expense' LIMIT 1").fetchone()[0]
            # Deliberate synthetic database state, bypassing clinical/financial posting:
            # We are testing report authorization, not approving a ledger.
            for i, (kind, fund, amount, cat) in enumerate((
                    ('receipt', normal, 10000, category),
                    ('receipt', bank, 50000, category),
                    ('receipt', restricted, 70000, category),
                    ('payment', normal, 3000, payment_category),
                    ('payment', bank, 20000, payment_category)), start=1):
                c.execute('''INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,
                    from_fund_id,shift,amount_piasters,description,status,created_by,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (f'REPORT-SYN-{i}', '2026-10-15', kind, dept_id, cat, fund, 'central',
                     amount, f'Synthetic report fixture {i}', 'approved', owner_id,
                     '2026-10-15T10:00:00+00:00'))
            c.commit()

        params = {'month': '2026-10'}
        def report(client):
            return ok(client.get('/api/reports', params=params))

        assert anonymous.get('/api/reports', params=params).status_code == 401
        own = report(owner)
        assert own['recognized_cash_service_revenue_piasters'] == 130000, own
        assert own['cash_paid_operating_items_piasters'] == 23000, own

        def check_viewer():
            v = report(viewer)
            assert v['recognized_cash_service_revenue_piasters'] == 10000, v
            assert v['scope'] == 'authorized_cash_only', v
            assert v['cash_paid_operating_items_piasters'] == 3000, v
            assert sum(d['amount_piasters'] for d in v['categories']) == 3000, v
            assert v['gl_departments'] == [], v
            for key in ('recognized_revenue_piasters', 'recognized_expenses_piasters',
                        'provisional_gl_result_piasters', 'approved_payroll_accruals_piasters',
                        'rough_margin_piasters'):
                assert v[key] is None, (key, v[key])
            ok(viewer.get('/api/accounting/patient-reconciliation', params={'period':'2026-10'}), 403)
            return v

        check_viewer()
        own_patient = ok(owner.get('/api/accounting/patient-reconciliation', params={'period':'2026-10'}))
        assert len(own_patient['checks']) == 3
        review = report(reviewer)
        assert review['recognized_cash_service_revenue_piasters'] == 10000, review
        assert review['cash_paid_operating_items_piasters'] == 3000, review
        # A reviewer's scoped cash cannot be netted against whole-hospital payroll.
        assert review['rough_margin_piasters'] is None, review

        def grant(enabled):
            ok(owner.post('/api/fund-access', headers=owner_headers, json={
                'user_id': reviewer_id, 'fund_id': bank, 'can_submit':enabled,
                'reason':'Explicit synthetic report visibility grant and revoke'}))

        grant(True)
        granted = report(reviewer)
        assert granted['recognized_cash_service_revenue_piasters'] == 60000, granted
        assert granted['cash_paid_operating_items_piasters'] == 23000, granted
        check_viewer()  # A viewer cannot inherit a reviewer's grant.
        grant(False)
        revoked = report(reviewer)
        assert revoked['recognized_cash_service_revenue_piasters'] == 10000, revoked
        assert revoked['cash_paid_operating_items_piasters'] == 3000, revoked
        assert report(owner)['recognized_cash_service_revenue_piasters'] == 130000
        assert ok(reviewer.get('/api/accounting/patient-reconciliation',
                               params={'period':'2026-10'}))['checks']
        print('PASS G2Y reports: protected bank/restricted fund excluded, viewer GL masked, grants live, patient recon restricted')


if __name__ == '__main__':
    run()
