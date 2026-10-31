"""G3E security regression: inventory rights do not confer patient-case rights.

Real FastAPI routes + isolated SQLite, synthetic patient data and direct HTTP
access; a revoked billing-point grant must hide case documents immediately.
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3e-privacy-') as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp) / 'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='g3e_synthetic_owner_password')
        for name in ('GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_TARGET'):
            os.environ.pop(name, None)
        from bootstrap import connect, initialize
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner, clerk, reviewer = (TestClient(app) for _ in range(3))

        def ok(response):
            assert response.status_code == 200, (response.status_code, response.text)
            return response.json()

        def login(client, name, password):
            csrf = ok(client.post('/api/login', json={
                'username': name, 'password': password}))['csrf']
            return {'X-CSRF-Token': csrf}

        oh = login(owner, 'owner', 'g3e_synthetic_owner_password')
        users = {}
        for name, role in (('g3e_clerk', 'clerk'), ('g3e_reviewer', 'reviewer')):
            users[name] = ok(owner.post('/api/users', headers=oh, json={
                'username': name, 'role': role,
                'password': 'g3e_synthetic_worker_password'}))['id']
        ch = login(clerk, 'g3e_clerk', 'g3e_synthetic_worker_password')
        rh = login(reviewer, 'g3e_reviewer', 'g3e_synthetic_worker_password')
        for name in users:
            ok(owner.post('/api/inventory/access', headers=oh, json={
                'user_id': users[name], 'can_prepare': name == 'g3e_clerk',
                'can_approve': name == 'g3e_reviewer',
                'reason': 'Synthetic restricted warehouse scope'}))

        points = ok(owner.get('/api/billing/config'))['points']
        point_a = next(p['id'] for p in points if p['kind'] == 'internal')
        point_b = next(p['id'] for p in points if p['kind'] == 'external')
        for point_id in (point_a, point_b):
            ok(owner.post(f'/api/billing/points/{point_id}/assign', headers=oh, json={
                'user_id': users['g3e_reviewer'], 'active': True}))
        ok(owner.post(f'/api/billing/points/{point_a}/assign', headers=oh, json={
            'user_id': users['g3e_clerk'], 'active': True}))

        today = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        cases = []
        for seq, point_id in enumerate((point_a, point_b), 1):
            patient_id = ok(owner.post('/api/billing/patients', headers=oh, json={
                'display_name': f'Synthetic scoped case {seq}',
                'request_id': f'g3e_privacy_patient_{seq:04d}'}))['id']
            cases.append(ok(owner.post('/api/billing/cases', headers=oh, json={
                'patient_id': patient_id, 'point_id': point_id,
                'kind': 'inpatient' if point_id == point_a else 'outpatient',
                'business_date': today, 'request_id': f'g3e_privacy_case_{seq:04d}'}))['id'])
        dept = next(d['id'] for d in ok(owner.get('/api/lookups'))['departments'] if d['code'] == 'IPD')
        vendor = ok(owner.post('/api/inventory/vendors', headers=oh, json={
            'code': 'G3E_PRIVACY_VENDOR', 'name': 'Synthetic privacy warehouse vendor'}))['id']
        item = ok(owner.post('/api/inventory/items', headers=oh, json={
            'code': 'G3E_PRIVACY_ITEM', 'name': 'Synthetic sealed supplies',
            'unit': 'piece'}))['id']
        receipt = ok(owner.post('/api/inventory/receipts', headers=oh, json={
            'vendor_id': vendor, 'received_on': today,
            'invoice_ref': 'G3E-SYNTH-RECEIPT-001',
            'evidence_ref': 'G3E-SYNTHETIC-STOCK-RECEIPT',
            'request_id': 'g3e_privacy_receipt_0001',
            'lines': [{'item_id': item, 'quantity': 15, 'unit_cost': '11.00'}]}))['id']
        ok(reviewer.post(f'/api/inventory/receipts/{receipt}/decision', headers=rh, json={
            'decision': 'approve', 'note': 'Independent synthetic stock review'}))

        issues = []
        for seq, case_id in enumerate((cases[0], cases[1], None), 1):
            issue_id = ok(owner.post('/api/inventory/issues', headers=oh, json={
                'department_id': dept, 'case_id': case_id, 'used_on': today,
                'evidence_ref': f'G3E-SYNTH-ISSUE-{seq:04d}',
                'request_id': f'g3e_privacy_issue_{seq:04d}',
                'lines': [{'item_id': item, 'quantity': 2}]}))['id']
            ok(reviewer.post(f'/api/inventory/issues/{issue_id}/decision', headers=rh, json={
                'decision': 'approve', 'note': 'Independent scoped inventory approval'}))
            issues.append(issue_id)
        returns = []
        for seq, issue_id in enumerate(issues[:2], 1):
            allocs = ok(owner.get(f'/api/inventory/issues/{issue_id}/returnable'))['allocations']
            ret = ok(owner.post('/api/inventory/returns', headers=oh, json={
                'issue_id': issue_id, 'returned_on': today,
                'evidence_ref': f'G3E-SYNTH-RETURN-{seq:04d}',
                'request_id': f'g3e_privacy_return_{seq:04d}',
                'lines': [{'issue_allocation_id': allocs[0]['issue_allocation_id'],
                           'quantity': 1}]}))['id']
            returns.append(ret)
        ok(reviewer.post(f'/api/inventory/returns/{returns[1]}/decision', headers=rh,
                         json={'decision': 'approve', 'note': 'Independent before revocation'}))

        # Reviewer's already-open session must not keep permission after revocation.
        pending_b = ok(owner.post('/api/inventory/issues', headers=oh, json={
            'department_id': dept, 'case_id': cases[1], 'used_on': today,
            'evidence_ref': 'G3E-SYNTH-PENDING-CASE-B',
            'request_id': 'g3e_privacy_issue_0004',
            'lines': [{'item_id': item, 'quantity': 1}]}))['id']
        ok(owner.post(f'/api/billing/points/{point_b}/assign', headers=oh, json={
            'user_id': users['g3e_reviewer'], 'active': False}))

        for client in (clerk, reviewer):
            overview = ok(client.get('/api/inventory/overview'))
            shown_issues = {r['id'] for r in overview['issues']}
            shown_returns = {r['id'] for r in overview['returns']}
            assert issues[0] in shown_issues and issues[2] in shown_issues, overview
            assert issues[1] not in shown_issues and pending_b not in shown_issues, \
                'Warehouse staff can read an unrelated patient-case issue'
            assert shown_returns == {returns[0]}, \
                'Warehouse overview exposes return linked to an unauthorized case'
            assert not any(r['case_id'] == cases[1] for r in overview['issues']), overview
        owner_view = ok(owner.get('/api/inventory/overview'))
        assert {issues[0], issues[1], issues[2], pending_b}.issubset(
            {r['id'] for r in owner_view['issues']})
        assert {returns[0], returns[1]}.issubset({r['id'] for r in owner_view['returns']})

        denied = reviewer.post(f'/api/inventory/issues/{pending_b}/decision', headers=rh,
                               json={'decision': 'approve', 'note': 'Unauthorized case approval attempt'})
        assert denied.status_code == 403, (denied.status_code, denied.text)
        # A decided foreign document must not reveal its status through a different error.
        for url in (f'/api/inventory/issues/{issues[1]}/decision',
                    f'/api/inventory/returns/{returns[1]}/decision'):
            result = reviewer.post(url, headers=rh,
                                   json={'decision': 'reject', 'note': 'Scoped review denied'})
            assert result.status_code == 403, (url, result.status_code, result.text)
        # A pending foreign issue must not reveal its existence via return validation.
        not_a_return = clerk.post('/api/inventory/returns', headers=ch, json={
            'issue_id': pending_b, 'returned_on': today,
            'evidence_ref': 'G3E-SYNTH-REJECTED-RETURN',
            'request_id': 'g3e_privacy_unpermitted_return_0001',
            'lines': [{'issue_allocation_id': 1, 'quantity': 1}]})
        assert not_a_return.status_code == 403, (not_a_return.status_code, not_a_return.text)
        with connect() as c:
            pending = c.execute('SELECT status,journal_id FROM inventory_issues WHERE id=?',
                                (pending_b,)).fetchone()
            assert pending['status'] == 'pending' and pending['journal_id'] is None
        assert reviewer.get(f'/api/inventory/issues/{issues[1]}/returnable').status_code == 403
        assert ok(reviewer.get(f'/api/inventory/issues/{issues[0]}/returnable'))['issue_id'] == issues[0]

        ok(owner.post(f'/api/billing/points/{point_a}/assign', headers=oh, json={
            'user_id': users['g3e_reviewer'], 'active': False}))
        isolated = ok(reviewer.get('/api/inventory/overview'))
        assert {r['id'] for r in isolated['issues']} == {issues[2]}, isolated
        assert isolated['returns'] == [], isolated
        assert {r['id'] for r in ok(owner.get('/api/inventory/overview'))['issues']} >= set(issues)
        print('PASS G3E overview case data scoping, live grant revocation, reviewer decision, and unlinked stock visibility')


if __name__ == '__main__':
    run()
