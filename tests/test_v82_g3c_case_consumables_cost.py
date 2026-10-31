"""TDD: actual FastAPI/SQLite case-specific approved FIFO cost, with dual grants."""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'cost.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_g3c_owner_password')
        for key in ('GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON'):
            os.environ.pop(key, None)
        from bootstrap import initialize, connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner, clerk, reviewer, ungranted, outsider = [TestClient(app) for _ in range(5)]

        def ok(response):
            assert response.status_code == 200, (response.status_code, response.text)
            return response.json()

        def auth(client, username, password):
            return {'X-CSRF-Token': ok(client.post('/api/login', json={
                'username': username, 'password': password}))['csrf']}

        oh = auth(owner, 'owner', 'synthetic_g3c_owner_password')
        ids = {}
        for name, role in (('cost_clerk', 'clerk'), ('cost_reviewer', 'reviewer'),
                           ('cost_ungranted', 'reviewer'), ('cost_outsider', 'reviewer')):
            ids[name] = ok(owner.post('/api/users', headers=oh, json={
                'username': name, 'role': role, 'password': 'synthetic_g3c_staff_password'}))['id']
        ch = auth(clerk, 'cost_clerk', 'synthetic_g3c_staff_password')
        rh = auth(reviewer, 'cost_reviewer', 'synthetic_g3c_staff_password')
        uh = auth(ungranted, 'cost_ungranted', 'synthetic_g3c_staff_password')
        xh = auth(outsider, 'cost_outsider', 'synthetic_g3c_staff_password')
        point = next(x['id'] for x in ok(owner.get('/api/billing/config'))['points'] if x['kind'] == 'internal')
        for name in ('cost_clerk', 'cost_reviewer', 'cost_ungranted'):
            ok(owner.post(f'/api/billing/points/{point}/assign', headers=oh,
                          json={'user_id': ids[name], 'active': True}))
        for name in ('cost_clerk', 'cost_reviewer', 'cost_outsider'):
            ok(owner.post('/api/inventory/access', headers=oh, json={
                'user_id': ids[name], 'can_prepare': name == 'cost_clerk',
                'can_approve': name != 'cost_clerk',
                'reason': 'Synthetic case cost authorization'}))
        today = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        dept = next(x['id'] for x in ok(owner.get('/api/lookups'))['departments'] if x['code'] == 'OR')
        patient = ok(owner.post('/api/billing/patients', headers=oh, json={
            'display_name': 'Synthetic surgical case only', 'request_id': 'g3c_test_patient_0001'}))['id']
        case = ok(owner.post('/api/billing/cases', headers=oh, json={
            'patient_id': patient, 'kind': 'operation', 'point_id': point,
            'business_date': today, 'request_id': 'g3c_test_case_0001'}))['id']
        vendor = ok(owner.post('/api/inventory/vendors', headers=oh, json={
            'code': 'G3C_VENDOR', 'name': 'Synthetic medical supplies vendor'}))['id']
        item = ok(owner.post('/api/inventory/items', headers=oh, json={
            'code': 'G3C_DRESSING', 'name': 'Synthetic sterile dressing item', 'unit': 'piece'}))['id']
        for seq, qty, unit in ((1, 3, '12.00'), (2, 5, '20.00')):
            rid = ok(clerk.post('/api/inventory/receipts', headers=ch, json={
                'vendor_id': vendor, 'received_on': today,
                'invoice_ref': f'G3C-SUPPLIER-INVOICE-{seq}',
                'evidence_ref': f'G3C-GOODS-RECEIPT-{seq}',
                'request_id': f'g3c_receipt_{seq:05d}',
                'lines': [{'item_id': item, 'quantity': qty, 'unit_cost': unit}]}))['id']
            ok(reviewer.post(f'/api/inventory/receipts/{rid}/decision', headers=rh, json={
                'decision': 'approve', 'note': 'Synthetic independent goods review'}))
        issue = {'department_id': dept, 'case_id': case, 'used_on': today,
                 'evidence_ref': 'G3C-SURGERY-SUPPLIES-ISSUE',
                 'request_id': 'g3c_case_issue_00001',
                 'lines': [{'item_id': item, 'quantity': 4}]}
        issue_id = ok(clerk.post('/api/inventory/issues', headers=ch, json=issue))['id']
        pending_id = ok(clerk.post('/api/inventory/issues', headers=ch, json={
            **issue, 'request_id': 'g3c_case_issue_00002',
            'evidence_ref': 'G3C-PENDING-ISSUE-REFERENCE',
            'lines': [{'item_id': item, 'quantity': 1}]}))['id']
        unlinked_id = ok(clerk.post('/api/inventory/issues', headers=ch, json={
            **issue, 'case_id': None, 'request_id': 'g3c_case_issue_00003',
            'evidence_ref': 'G3C-DEPARTMENT-STOCK-ISSUE',
            'lines': [{'item_id': item, 'quantity': 1}]}))['id']
        ok(reviewer.post(f'/api/inventory/issues/{issue_id}/decision', headers=rh, json={
            'decision': 'approve', 'note': 'Synthetic signed case issue review'}))
        ok(reviewer.post(f'/api/inventory/issues/{unlinked_id}/decision', headers=rh, json={
            'decision': 'approve', 'note': 'Synthetic separate department issue review'}))
        route = f'/api/inventory/cases/{case}/cost'
        with connect() as c:
            before = (c.execute('SELECT COUNT(*) FROM inventory_issue_allocations').fetchone()[0],
                      c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0])
        summary = ok(owner.get(route))
        assert summary['case_id'] == case and summary['total_cost_piasters'] == 5600, summary
        assert summary['approved_issue_count'] == 1 and summary['pending_issue_count'] == 1, summary
        assert summary['source'] == 'approved_fifo_consumables_only', summary
        lines = summary['lines']
        assert len(lines) == 1, lines
        assert lines[0]['item_id'] == item and lines[0]['quantity'] == 4, lines
        assert lines[0]['cost_piasters'] == 5600 and lines[0]['issue_id'] == issue_id, lines
        assert lines[0]['department_id'] == dept and lines[0]['used_on'] == today, lines
        assert 'patient_name' not in str(summary) and 'patient_code' not in str(summary)
        assert ok(clerk.get(route))['total_cost_piasters'] == 5600
        assert ok(reviewer.get(route))['total_cost_piasters'] == 5600
        assert ungranted.get(route).status_code == 403, 'Billing point alone must not expose FIFO prices'
        assert outsider.get(route).status_code == 403, 'Inventory grant alone must not expose patient-case cost'
        assert owner.get('/api/inventory/cases/9999999/cost').status_code == 404
        ok(owner.post('/api/inventory/access', headers=oh, json={
            'user_id': ids['cost_reviewer'], 'can_prepare': False,
            'can_approve': False, 'reason': 'Synthetic immediate inventory revocation'}))
        assert reviewer.get(route).status_code == 403
        with connect() as c:
            after = (c.execute('SELECT COUNT(*) FROM inventory_issue_allocations').fetchone()[0],
                     c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0])
            assert before == after, (before, after)
            assert c.execute('SELECT status FROM inventory_issues WHERE id=?', (pending_id,)).fetchone()[0] == 'pending'
        print('PASS G3C case FIFO costs from approved immutable issues, no phantom costs, dual grants and revocation')


if __name__ == '__main__':
    run()
