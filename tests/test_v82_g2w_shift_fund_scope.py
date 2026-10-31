"""G2W: guarded shift details and evidence follow the current restricted-fund grant.

Uses real HTTP and synthetic SQLite; no hospital data and no fake permission mocks.
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as workdir:
        os.environ.update(RAMSES_DB_PATH=str(Path(workdir) / 'g2w.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_g2w_owner_password')
        from bootstrap import initialize, connect
        from app import app
        from fastapi.testclient import TestClient
        initialize()
        owner, reviewer, viewer = [TestClient(app) for _ in range(3)]

        def ok(response, status=200):
            assert response.status_code == status, (status, response.status_code, response.text[:300])
            return response.json() if status == 200 else None

        def login(client, name, password):
            return {'X-CSRF-Token': ok(client.post('/api/login', json={
                'username': name, 'password': password}))['csrf']}

        owner_headers = login(owner, 'owner', 'synthetic_g2w_owner_password')
        reviewer_id = ok(owner.post('/api/users', headers=owner_headers, json={
            'username': 'synthetic_g2w_reviewer', 'role': 'reviewer',
            'password': 'synthetic_g2w_reviewer_password'}))['id']
        ok(owner.post('/api/users', headers=owner_headers, json={
            'username': 'synthetic_g2w_viewer', 'role': 'viewer',
            'password': 'synthetic_g2w_viewer_password'}))
        reviewer_headers = login(reviewer, 'synthetic_g2w_reviewer', 'synthetic_g2w_reviewer_password')
        login(viewer, 'synthetic_g2w_viewer', 'synthetic_g2w_viewer_password')

        restricted_id = ok(owner.post('/api/funds', headers=owner_headers, json={
            'code': 'secret_till', 'name': 'Synthetic restricted cash drawer',
            'kind': 'cash', 'restricted_cash': True}))['id']
        unrestricted_id = ok(owner.post('/api/funds', headers=owner_headers, json={
            'code': 'shared_till', 'name': 'Synthetic general cash drawer',
            'kind': 'cash'}))['id']
        ok(owner.post('/api/cashier/points', headers=owner_headers, json={
            'code': 'G2W_RESTRICTED', 'name': 'Synthetic restricted station',
            'fund_id': restricted_id, 'slots': [
                {'code': 'morning', 'name': 'Morning', 'start': '08:00'}],
            'reason': 'Testing current scoped finance authorization'}))
        today = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        closed_month = today[:7]
        secret_shift = ok(owner.post('/api/shifts/open', headers=owner_headers, json={
            'business_date': today, 'shift': 'morning', 'fund_id': restricted_id}))['id']
        regular_shift = ok(owner.post('/api/shifts/open', headers=owner_headers, json={
            'business_date': today, 'shift': 'morning', 'fund_id': unrestricted_id}))['id']
        upload = owner.post(f'/api/cashier/shifts/{secret_shift}/attachments/report',
                            headers=owner_headers, files={'file': (
                               'synthetic-shift.pdf', b'%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF',
                               'application/pdf')})
        doc_id = ok(upload)['id']
        with connect() as db_conn:
            synthetic_case = db_conn.execute('''INSERT INTO shift_variance_cases
                (shift_session_id,variance_piasters,explanation,proposed_by,proposed_at,status)
                VALUES (?,?,?,?,?,?)''',(secret_shift,-100,'Synthetic confidential shortage',
                                          ok(owner.get('/api/me'))['id'],today+'T09:00:00Z','approved')).lastrowid

        def visible_shift_ids():
            return [item['id'] for item in ok(reviewer.get('/api/shifts',
                          params={'month': closed_month}))['items']]

        def reviewer_shift_record():
            return next(item for item in ok(reviewer.get('/api/shifts',
                params={'month':closed_month}))['items'] if item['id']==secret_shift)

        def expect_hidden():
            ids = visible_shift_ids()
            assert regular_shift in ids, f'Normal cash shift should stay readable: {ids}'
            assert secret_shift not in ids, f'Restricted shift leaked through listing: {ids}'
            summary = ok(reviewer.get('/api/shifts/day-summary',
                                     params={'business_date': today}))
            assert secret_shift not in [item['id'] for item in summary['stations']], summary
            coverage = ok(reviewer.get('/api/shifts/coverage',
                                       params={'month': closed_month}))
            assert restricted_id not in [item['fund_id'] for item in coverage['points']], coverage['points']
            assert secret_shift not in [item.get('session_id') for item in coverage['items']]
            assert restricted_id not in [p['fund_id'] for p in ok(reviewer.get('/api/cashier/plans'))['points']]
            variance = ok(reviewer.get('/api/reconciliation/variances',
                                       params={'month':closed_month}))
            assert synthetic_case not in [item['id'] for item in variance['items']], variance
            shortage = ok(reviewer.get('/api/cashier/shortage-repayments'))
            assert synthetic_case not in [item['case_id'] for item in shortage['cases']], shortage
            for url in (
                    f'/api/shifts/{secret_shift}/movements',
                    f'/api/shifts/{secret_shift}/count-history',
                    f'/api/shifts/{secret_shift}/daily-report',
                    f'/api/cashier/shifts/{secret_shift}/attachments',
                    f'/api/cashier/shift-attachments/{doc_id}/download'):
                ok(reviewer.get(url), 403)
            ok(reviewer.post(f'/api/shifts/{secret_shift}/review',headers=reviewer_headers,
                json={'decision': 'approve', 'reason': 'Synthetic negative grant test'}),403)
            ok(reviewer.post(f'/api/shifts/{secret_shift}/handoff',headers=reviewer_headers,
                json={'counted_amount':'0','decision':'accept','note':'Permission denial'}),403)
            ok(reviewer.post(f'/api/shifts/{secret_shift}/variance-propose',headers=reviewer_headers,
                json={'explanation':'Synthetic unauthorized proposal to test fund grant'}),403)
            ok(reviewer.post(f'/api/shifts/{secret_shift}/variance-decision',headers=reviewer_headers,
                json={'decision':'approve','reason':'Synthetic denial of scope'}),403)

        # Disallowed by default, despite reviewer role; owner and viewer are distinct.
        assert secret_shift in [v['id'] for v in ok(owner.get('/api/shifts',
                                                    params={'month': closed_month}))['items']]
        ok(viewer.get(f'/api/cashier/shifts/{secret_shift}/attachments'),403)
        ok(owner.post('/api/cashier/variance-permissions',headers=owner_headers,json={
            'user_id':reviewer_id,'can_approve':True,
            'reason':'Synthetic exception granted independently for security negative test'}))
        expect_hidden()

        def grant(submit, approve):
            ok(owner.post('/api/fund-access', headers=owner_headers, json={
                'user_id': reviewer_id, 'fund_id': restricted_id,
                'can_submit': submit, 'can_approve': approve,
                'reason': 'Explicit scoped shift grant and revocation verification'}))

        grant(True, False)
        assert secret_shift in visible_shift_ids(), 'Reviewer with submission grant must read that fund'
        assert reviewer_shift_record()['can_review'] is False, 'Submit-only reviewer should not see approve action'
        assert restricted_id in [p['fund_id'] for p in ok(reviewer.get('/api/cashier/plans'))['points']]
        ok(reviewer.get(f'/api/shifts/{secret_shift}/daily-report'))
        assert reviewer.get(f'/api/cashier/shift-attachments/{doc_id}/download').status_code == 200
        ok(reviewer.post(f'/api/shifts/{secret_shift}/review',headers=reviewer_headers,
               json={'decision':'approve','reason':'No review grant'}),403)
        grant(False, True)
        assert secret_shift in visible_shift_ids()
        assert reviewer_shift_record()['can_review'] is True
        assert synthetic_case in [item['id'] for item in ok(reviewer.get('/api/reconciliation/variances',
                                                     params={'month':closed_month}))['items']]
        ok(reviewer.get(f'/api/shifts/{secret_shift}/movements'))
        # Shift itself remains open; authorization is valid but financial decision cannot proceed.
        ok(reviewer.post(f'/api/shifts/{secret_shift}/review',headers=reviewer_headers,
               json={'decision':'approve','reason':'Not yet submitted'}),409)
        grant(False, False)
        expect_hidden()
        print('PASS G2W restricted shift reads, attachments, day summary, review authorization and live revocation')

if __name__ == '__main__':
    run()
