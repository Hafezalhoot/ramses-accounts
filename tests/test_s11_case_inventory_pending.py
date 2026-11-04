"""Pending case consumables must be resolved before financial case closure.

Real API/SQLite regression: omitting pending inventory issues from clearance
readiness strands them after case close, because their review requires an open
case. Exercise request-time and independent approval-time checks without money.
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as folder:
        os.environ.update(
            RAMSES_DB_PATH=str(Path(folder) / 'case_inventory.sqlite3'),
            RAMSES_ADMIN_USER='owner',
            RAMSES_ADMIN_PASSWORD='synthetic_s11_case_owner_password',
        )
        for key in ('GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON'):
            os.environ.pop(key, None)
        from bootstrap import initialize, connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient

        owner, clerk, reviewer = [TestClient(app) for _ in range(3)]

        def ok(response, status=200):
            assert response.status_code == status, (response.status_code, response.text, status)
            return response.json()

        def login(client, name, password):
            return {'X-CSRF-Token': ok(client.post('/api/login', json={
                'username': name, 'password': password}))['csrf']}

        oh = login(owner, 'owner', 'synthetic_s11_case_owner_password')
        users = {}
        for name, role in (('s11_case_clerk', 'clerk'), ('s11_case_reviewer', 'reviewer')):
            users[name] = ok(owner.post('/api/users', headers=oh, json={
                'username': name, 'role': role, 'password': 'synthetic_s11_case_staff_password'}))['id']
        ch = login(clerk, 's11_case_clerk', 'synthetic_s11_case_staff_password')
        rh = login(reviewer, 's11_case_reviewer', 'synthetic_s11_case_staff_password')
        point = next(p['id'] for p in ok(owner.get('/api/billing/config'))['points']
                     if p['kind'] == 'internal')
        for name, user_id in users.items():
            ok(owner.post(f'/api/billing/points/{point}/assign', headers=oh,
                          json={'user_id': user_id, 'active': True}))
            ok(owner.post('/api/inventory/access', headers=oh, json={
                'user_id': user_id, 'can_prepare': name == 's11_case_clerk',
                'can_approve': name == 's11_case_reviewer',
                'reason': 'Synthetic S11 case consumables review'}))
        day = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        department = next(d['id'] for d in ok(owner.get('/api/lookups'))['departments']
                          if d['code'] == 'OR')
        item = ok(owner.post('/api/inventory/items', headers=oh, json={
            'code': 'S11_PENDING_SUPPLY', 'name': 'Synthetic unused surgical supply', 'unit': 'piece'}))['id']

        def new_case(sequence):
            patient = ok(owner.post('/api/billing/patients', headers=oh, json={
                'display_name': f'Synthetic S11 case {sequence}',
                'request_id': f's11_case_patient_{sequence:04d}'}))['id']
            return ok(owner.post('/api/billing/cases', headers=oh, json={
                'patient_id': patient, 'kind': 'operation', 'point_id': point,
                'business_date': day, 'request_id': f's11_inventory_case_{sequence:04d}'}))['id']

        def pending_issue(case_id, sequence):
            return ok(clerk.post('/api/inventory/issues', headers=ch, json={
                'department_id': department, 'case_id': case_id, 'used_on': day,
                'evidence_ref': f'SYN-S11-UNUSED-STOCK-{sequence}',
                'request_id': f's11_case_stock_issue_{sequence:04d}',
                'lines': [{'item_id': item, 'quantity': 1}]}))['id']

        def clearance(case_id, sequence, mode='no_charge'):
            return owner.post(f'/api/case-settlement/cases/{case_id}/request', headers=oh, json={
                'mode': mode, 'request_id': f's11_case_clearance_{sequence:04d}',
                'evidence_reference': f'SYN-S11-CLEARANCE-{sequence}',
                'note': 'Synthetic financial case review independent of clinical discharge'})

        def financial_sources():
            with connect() as c:
                return tuple(c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                             for table in ('gl_journals', 'gl_lines', 'vouchers', 'fund_movements'))

        # A pending issue is a live source document even on an otherwise empty case.
        empty_case = new_case(1)
        issue = pending_issue(empty_case, 1)
        before = financial_sources()
        pre = ok(owner.get(f'/api/case-settlement/cases/{empty_case}'))['preflight']
        assert pre['no_charge_ready'] is False, 'Pending consumables issue allowed no-charge closure'
        assert pre['ready'] is False
        assert pre['pending_inventory_issues'] == 1
        assert any('صرف مستلزمات' in reason for reason in pre['blockers']), pre
        ok(clearance(empty_case, 1), 409)
        with connect() as c:
            assert c.execute('SELECT status FROM billing_cases WHERE id=?', (empty_case,)).fetchone()[0] == 'open'
            assert c.execute('SELECT status FROM inventory_issues WHERE id=?', (issue,)).fetchone()[0] == 'pending'
            assert c.execute('SELECT COUNT(*) FROM billing_case_clearance_requests WHERE case_id=?',
                             (empty_case,)).fetchone()[0] == 0
        assert financial_sources() == before

        # Independent rejection of the unused issue clears only its own case.
        ok(reviewer.post(f'/api/inventory/issues/{issue}/decision', headers=rh, json={
            'decision': 'reject', 'note': 'Unused supply request independently rejected before cancellation'}))
        unrelated_case = new_case(2)
        pending_issue(unrelated_case, 2)
        assert ok(owner.get(f'/api/case-settlement/cases/{empty_case}'))['preflight']['no_charge_ready']
        req = ok(clearance(empty_case, 2))
        ok(owner.post(f'/api/case-settlement/requests/{req["id"]}/decision', headers=oh, json={
            'decision': 'approve', 'note': 'Requester must never approve their own cancellation'}), 403)
        ok(reviewer.post(f'/api/case-settlement/requests/{req["id"]}/decision', headers=rh, json={
            'decision': 'approve', 'note': 'Independent cancellation after unused inventory issue rejection'}))
        assert financial_sources() == before

        # A request already pending must be rechecked if a stock issue arrives later.
        late_case = new_case(3)
        late_req = ok(clearance(late_case, 3))
        late_issue = pending_issue(late_case, 3)
        before = financial_sources()
        ok(reviewer.post(f'/api/case-settlement/requests/{late_req["id"]}/decision', headers=rh, json={
            'decision': 'approve', 'note': 'Late consumables issue must invalidate financial readiness'}), 409)
        # Rejecting a clearance request is still permitted; it does not close the case.
        ok(reviewer.post(f'/api/case-settlement/requests/{late_req["id"]}/decision', headers=rh, json={
            'decision': 'reject', 'note': 'Reject financial cancellation while consumables need review'}))
        with connect() as c:
            assert c.execute('SELECT status FROM billing_cases WHERE id=?', (late_case,)).fetchone()[0] == 'open'
            assert c.execute('SELECT status FROM inventory_issues WHERE id=?', (late_issue,)).fetchone()[0] == 'pending'
        assert financial_sources() == before

        # A zero-due, fully credited invoice is otherwise ready for settled clearance.
        settled_case = new_case(4)
        service = ok(owner.post('/api/billing/services', headers=oh, json={
            'code': 'S11_CASE_SERVICE', 'name': 'Synthetic canceled surgical charge',
            'department_id': department}))['id']
        ok(owner.post(f'/api/billing/services/{service}/prices', headers=oh,
                      json={'valid_from': day, 'amount': '10'}))
        line = ok(clerk.post(f'/api/billing/cases/{settled_case}/services', headers=ch, json={
            'service_id': service, 'quantity': 1, 'request_id': 's11_settled_service_0001'}))['id']
        ok(reviewer.post(f'/api/billing/lines/{line}/fulfill', headers=rh))
        draft = ok(clerk.post(f'/api/billing/cases/{settled_case}/drafts', headers=ch,
                              json={'request_id': 's11_settled_draft_0001'}))['id']
        invoice = ok(clerk.post(f'/api/billing/drafts/{draft}/issue', headers=ch,
                                json={'request_id': 's11_settled_invoice_0001'}))['id']
        credit = ok(clerk.post(f'/api/billing/cases/{settled_case}/credits', headers=ch, json={
            'invoice_id': invoice, 'amount': '10', 'reason': 'Synthetic unused service credited independently',
            'request_id': 's11_settled_credit_0001'}))['id']
        ok(reviewer.post(f'/api/billing/credits/{credit}/decision', headers=rh,
                         json={'decision': 'approve', 'note': 'Independent credit before case closure'}))
        assert ok(owner.get(f'/api/case-settlement/cases/{settled_case}'))['preflight']['ready']
        settled_req = ok(clearance(settled_case, 4, mode='settled'))
        settled_issue = pending_issue(settled_case, 4)
        before = financial_sources()
        pre = ok(owner.get(f'/api/case-settlement/cases/{settled_case}'))['preflight']
        assert pre['ready'] is False and pre['pending_inventory_issues'] == 1, pre
        ok(reviewer.post(f'/api/case-settlement/requests/{settled_req["id"]}/decision', headers=rh, json={
            'decision': 'approve', 'note': 'Recheck settled case pending consumables before final close'}), 409)
        ok(reviewer.post(f'/api/inventory/issues/{settled_issue}/decision', headers=rh, json={
            'decision': 'reject', 'note': 'Unused settled-case consumables independently rejected'}))
        ok(reviewer.post(f'/api/case-settlement/requests/{settled_req["id"]}/decision', headers=rh, json={
            'decision': 'approve', 'note': 'Independent final close after consumables decision resolved'}))
        assert financial_sources() == before
        print('PASS S11 pending case consumables block no-charge/settled clearance and stale approval; '
              'independent rejection, unrelated cases and cash/GL remain unchanged')


if __name__ == '__main__':
    run()
