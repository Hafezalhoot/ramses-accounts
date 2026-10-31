"""TDD: independent approved partial returns retain original lot cost, case scope and GL."""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3d-returns-') as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp) / 'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_owner_return_password')
        for key in ('GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_TARGET'):
            os.environ.pop(key, None)
        from bootstrap import connect, initialize
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner, clerk, reviewer, outsider = (TestClient(app) for _ in range(4))

        def ok(response):
            assert response.status_code == 200, (response.status_code, response.text)
            return response.json()

        def auth(client, username, password):
            return {'X-CSRF-Token': ok(client.post('/api/login', json={
                'username': username, 'password': password}))['csrf']}

        oh = auth(owner, 'owner', 'synthetic_owner_return_password')
        names = [('stock_return_clerk', 'clerk'), ('stock_return_reviewer', 'reviewer'),
                 ('stock_return_outsider', 'reviewer')]
        ids = {name: ok(owner.post('/api/users', headers=oh, json={
            'username': name, 'password': 'synthetic_return_worker_pw',
            'role': role}))['id'] for name, role in names}
        ch = auth(clerk, names[0][0], 'synthetic_return_worker_pw')
        rh = auth(reviewer, names[1][0], 'synthetic_return_worker_pw')
        xh = auth(outsider, names[2][0], 'synthetic_return_worker_pw')
        for name in ('stock_return_clerk', 'stock_return_reviewer', 'stock_return_outsider'):
            ok(owner.post('/api/inventory/access', headers=oh, json={
                'user_id': ids[name], 'can_prepare': name.endswith('clerk'),
                'can_approve': not name.endswith('clerk'),
                'reason': 'Synthetic independently reviewed supply return'}))
        point = next(x['id'] for x in ok(owner.get('/api/billing/config'))['points']
                     if x['kind'] == 'internal')
        for name in ('stock_return_clerk', 'stock_return_reviewer'):
            ok(owner.post(f'/api/billing/points/{point}/assign', headers=oh, json={
                'user_id': ids[name], 'active': True}))
        day = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        dept = next(x['id'] for x in ok(owner.get('/api/lookups'))['departments']
                    if x['code'] == 'OR')
        patient = ok(owner.post('/api/billing/patients', headers=oh, json={
            'display_name': 'Synthetic return case',
            'request_id': 'g3d_patient_return_001'}))['id']
        case_id = ok(owner.post('/api/billing/cases', headers=oh, json={
            'patient_id': patient, 'point_id': point, 'kind': 'operation',
            'business_date': day, 'request_id': 'g3d_case_return_001'}))['id']
        vendor = ok(owner.post('/api/inventory/vendors', headers=oh, json={
            'code': 'G3D_RETURN_VENDOR', 'name': 'Synthetic return supplier'}))['id']
        item = ok(owner.post('/api/inventory/items', headers=oh, json={
            'code': 'G3D_RETURN_ITEM', 'name': 'Synthetic unused sterile dressing',
            'unit': 'piece'}))['id']

        for seq, qty, cost in ((1, 3, '12.00'), (2, 5, '20.00')):
            receipt = ok(clerk.post('/api/inventory/receipts', headers=ch, json={
                'vendor_id': vendor, 'received_on': day,
                'invoice_ref': f'G3D-RECEIPT-SUPPLIER-{seq}',
                'evidence_ref': f'G3D-SYNTH-RECEIPT-{seq}',
                'request_id': f'g3d_return_receipt_{seq:04d}',
                'lines': [{'item_id': item, 'quantity': qty, 'unit_cost': cost}]}))['id']
            ok(reviewer.post(f'/api/inventory/receipts/{receipt}/decision', headers=rh,
                             json={'decision': 'approve', 'note': 'Synthetic goods received independently'}))
        issue_id = ok(clerk.post('/api/inventory/issues', headers=ch, json={
            'department_id': dept, 'case_id': case_id, 'used_on': day,
            'evidence_ref': 'G3D-SYNTH-CASE-ISSUE-001',
            'request_id': 'g3d_return_issue_0001',
            'lines': [{'item_id': item, 'quantity': 4}]}))['id']
        ok(reviewer.post(f'/api/inventory/issues/{issue_id}/decision', headers=rh,
                         json={'decision': 'approve', 'note': 'Synthetic issue reviewed by second person'}))
        before = ok(owner.get(f'/api/inventory/cases/{case_id}/cost'))
        assert before['total_cost_piasters'] == 5600, before
        with connect() as c:
            allocs = c.execute('''SELECT a.id,a.quantity,l.unit_cost_piasters FROM inventory_issue_allocations a
                JOIN inventory_receipt_lines l ON l.id=a.receipt_line_id
                WHERE a.issue_id=? ORDER BY l.unit_cost_piasters''', (issue_id,)).fetchall()
            assert [(a['quantity'], a['unit_cost_piasters']) for a in allocs] == [(3, 1200), (1, 2000)]
            src_allocation = allocs[0]['id']
            wrong_allocation = allocs[1]['id']
            journals_before = c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
        source = ok(clerk.get(f'/api/inventory/issues/{issue_id}/returnable', headers=ch))
        assert source['issue_id'] == issue_id and len(source['allocations']) == 2, source
        assert outsider.get(f'/api/inventory/issues/{issue_id}/returnable', headers=xh).status_code == 403
        payload = {'issue_id': issue_id, 'returned_on': day,
                   'evidence_ref': 'G3D-SYNTH-UNUSED-SUPPLIES-RETURN',
                   'request_id': 'g3d_return_00001',
                   'lines': [{'issue_allocation_id': src_allocation, 'quantity': 2}]}
        assert outsider.post('/api/inventory/returns', headers=xh, json=payload).status_code == 403
        return_id = ok(clerk.post('/api/inventory/returns', headers=ch, json=payload))['id']
        assert ok(clerk.post('/api/inventory/returns', headers=ch, json=payload))['replayed']
        assert clerk.post(f'/api/inventory/returns/{return_id}/decision', headers=ch,
                          json={'decision': 'approve', 'note': 'Cannot review own return'}).status_code == 403
        assert ok(owner.get('/api/inventory/overview'))['items'][0]['quantity_on_hand'] == 4
        assert ok(owner.get(f'/api/inventory/cases/{case_id}/cost'))['total_cost_piasters'] == 5600
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0] == journals_before
        approved = ok(reviewer.post(f'/api/inventory/returns/{return_id}/decision', headers=rh,
                                    json={'decision': 'approve', 'note': 'Verified physically unused and sealed supplies'}))
        assert approved['status'] == 'approved' and approved['cost_piasters'] == 2400, approved
        assert approved['journal_id'], approved
        denied_reverse=owner.post(f"/api/accounting/journals/{approved['journal_id']}/reverse", headers=oh,
            json={'date':day,'reason':'Attempt to manually erase immutable inventory return'})
        assert denied_reverse.status_code == 409, (denied_reverse.status_code,denied_reverse.text)
        assert reviewer.post(f'/api/inventory/returns/{return_id}/decision', headers=rh,
                             json={'decision': 'approve', 'note': 'Duplicate return approval'}).status_code == 409
        stock = ok(owner.get('/api/inventory/overview'))['items'][0]
        assert stock['quantity_on_hand'] == 6 and stock['value_piasters'] == 10400, stock
        cost = ok(owner.get(f'/api/inventory/cases/{case_id}/cost'))
        assert cost['total_cost_piasters'] == 3200 and cost['total_returned_piasters'] == 2400, cost
        assert cost['lines'][0]['returned_quantity'] == 2 and cost['lines'][0]['net_quantity'] == 2, cost
        assert cost['lines'][0]['cost_piasters'] == 3200, cost
        assert ok(owner.get('/api/inventory/reconciliation', params={'period': day[:7]}))['matched']
        with connect() as c:
            journal = c.execute('''SELECT ac.code,SUM(l.debit_piasters-l.credit_piasters) signed
                FROM gl_lines l JOIN gl_accounts ac ON ac.id=l.account_id
                WHERE l.journal_id=? GROUP BY ac.code''', (approved['journal_id'],)).fetchall()
            assert {r['code']: r['signed'] for r in journal} == {'1100': 2400, '5100': -2400}, journal
            for statement, args in (
                ('UPDATE inventory_issue_returns SET evidence_ref=? WHERE id=?', ('TAMPERED', return_id)),
                ('DELETE FROM inventory_return_lines WHERE return_id=?', (return_id,)),
                ('DELETE FROM inventory_issue_returns WHERE id=?', (return_id,)),
            ):
                try:
                    c.execute(statement, args)
                except sqlite3.IntegrityError:
                    c.rollback()
                else:
                    raise AssertionError('Approved return is mutable: ' + statement)
        excess = {**payload, 'request_id': 'g3d_return_00002',
                  'lines': [{'issue_allocation_id': src_allocation, 'quantity': 2}]}
        response = clerk.post('/api/inventory/returns', headers=ch, json=excess)
        assert response.status_code == 409, (response.status_code, response.text)
        bogus = {**payload, 'request_id': 'g3d_return_00003',
                 'lines': [{'issue_allocation_id': 9999999, 'quantity': 1}]}
        assert clerk.post('/api/inventory/returns', headers=ch, json=bogus).status_code == 409
        # G3F: the earlier financial approval restores hospital ownership, NOT
        # authorization for reuse. A separately credentialed clinician must
        # release the exact immutable returned lot before FIFO can see it.
        stock_now=ok(owner.get('/api/inventory/overview'))['items'][0]
        assert stock_now['quarantined_quantity']==2 and stock_now['available_quantity']==4,stock_now
        med_id=ok(owner.post('/api/users',headers=oh,json={
            'username':'g3f_return_clinician','role':'clinician',
            'password':'synthetic_g3f_return_clinician_pw'}))['id']
        ok(owner.post('/api/billing/clinical/identity-review',headers=oh,json={
            'user_id':med_id,'professional_name':'Synthetic Return Clinician',
            'registration_reference':'SYN-G3F-REVIEWER-REF-0001',
            'review_note':'Synthetic owner credential check before lot release',
            'approved':True,'current_password':'synthetic_owner_return_password'}))
        ok(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'user_id':med_id,'department_id':dept,'active':True}))
        med=TestClient(app)
        mh=auth(med,'g3f_return_clinician','synthetic_g3f_return_clinician_pw')
        review_items=ok(med.get('/api/inventory/inspections/queue'))['items']
        target=next(x for x in review_items if x['return_id']==return_id)
        assert target['quantity']==2
        ok(med.post(f'/api/inventory/inspections/{target["return_line_id"]}/decision',headers=mh,json={
            'decision':'release','inspected_on':day,'evidence_ref':'SYN-G3F-PACKAGE-AND-IC-REVIEW',
            'note':'Synthetic untouched return and physical packaging confirmed',
            'unused_confirmed':True,'packaging_intact':True,'infection_control_clearance':True}))
        # Other lots cannot be silently substituted; quantity returns to the original FIFO lot.
        next_issue = ok(clerk.post('/api/inventory/issues', headers=ch, json={
            'department_id': dept, 'case_id': case_id, 'used_on': day,
            'evidence_ref': 'G3D-AFTER-RETURN-ISSUE-002',
            'request_id': 'g3d_return_issue_0002',
            'lines': [{'item_id': item, 'quantity': 2}]}))['id']
        next_approved = ok(reviewer.post(f'/api/inventory/issues/{next_issue}/decision', headers=rh,
                                         json={'decision': 'approve', 'note': 'Use restored returned lot for next case issue'}))
        assert next_approved['cost_piasters'] == 2400, next_approved
        assert ok(owner.get('/api/inventory/overview'))['items'][0]['value_piasters'] == 8000
        assert ok(owner.get('/api/inventory/overview'))['items'][0]['quantity_on_hand'] == 4
        assert ok(owner.get('/api/inventory/reconciliation', params={'period': day[:7]}))['matched']
        # Pending return must block month close, rejected return must not affect stock or GL.
        pending = {**payload, 'request_id': 'g3d_return_00004',
                   'lines': [{'issue_allocation_id': wrong_allocation, 'quantity': 1}]}
        pending_id = ok(clerk.post('/api/inventory/returns', headers=ch, json=pending))['id']
        from inventory import month_close_inventory_issue
        from case_settlement import case_preflight
        with connect() as c:
            assert month_close_inventory_issue(c, day[:7]) is not None
            row=c.execute('SELECT * FROM billing_cases WHERE id=?',(case_id,)).fetchone()
            preflight=case_preflight(c,row)
            assert preflight['pending_inventory_returns']==1, preflight
            assert any('مرتجع' in reason for reason in preflight['blockers']), preflight
            # A direct SQLite status update must not bypass pending-return clearance.
            c.execute('SAVEPOINT g3d_case_pending_close')
            try:
                c.execute('''INSERT INTO billing_case_clearance_requests
                    (case_id,point_id,evidence_reference,note,requested_by,requested_at,
                     status,reviewed_by,reviewed_at,closed_on,clearance_mode)
                     VALUES (?,?,?,?,?,?,'approved',?,?,?,'settled')''',
                     (case_id,point,'G3D-SYNTH-CASE-CLR-001',
                      'Synthetic reviewed financial case close',ids['stock_return_clerk'],
                      day,ids['stock_return_reviewer'],day,day))
                try:
                    c.execute("UPDATE billing_cases SET status='closed' WHERE id=?",(case_id,))
                except sqlite3.IntegrityError as error:
                    assert 'pending inventory' in str(error).lower(), str(error)
                else:
                    raise AssertionError('Pending inventory return bypassed case financial close')
            finally:
                c.execute('ROLLBACK TO SAVEPOINT g3d_case_pending_close')
                c.execute('RELEASE SAVEPOINT g3d_case_pending_close')
        ok(reviewer.post(f'/api/inventory/returns/{pending_id}/decision', headers=rh,
                         json={'decision': 'reject', 'note': 'Not physically verified by independent reviewer'}))
        with connect() as c:
            assert month_close_inventory_issue(c, day[:7]) is None
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        # Point revocation must also block replay of a previously prepared return;
        # inventory permission by itself is not patient-case permission.
        # Concurrent physical return requests for the final original unit must serialize.
        from concurrent.futures import ThreadPoolExecutor
        def race(seq):
            client=TestClient(app)
            header=auth(client,'stock_return_clerk','synthetic_return_worker_pw')
            response=client.post('/api/inventory/returns',headers=header,json={
                **payload,'request_id':f'g3d_concurrent_return_{seq:04d}',
                'lines':[{'issue_allocation_id':src_allocation,'quantity':1}]})
            return response.status_code,response.json()
        with ThreadPoolExecutor(max_workers=2) as executor:
            attempts=list(executor.map(race,(1,2)))
        assert sorted(x[0] for x in attempts)==[200,409],attempts
        accepted=next(x[1]['id'] for x in attempts if x[0]==200)
        ok(reviewer.post(f'/api/inventory/returns/{accepted}/decision',headers=rh,
            json={'decision':'reject','note':'Reject spare unit after concurrent reservation check'}))
        with connect() as c:
            assert month_close_inventory_issue(c,day[:7]) is None
        assert ok(owner.get('/api/inventory/reconciliation',params={'period':day[:7]}))['matched']
        ok(owner.post(f'/api/billing/points/{point}/assign', headers=oh, json={
            'user_id': ids['stock_return_clerk'], 'active': False}))
        assert clerk.post('/api/inventory/returns', headers=ch, json=payload).status_code == 403, \
            'Idempotent replay bypassed case grant revocation'
        ok(owner.post('/api/inventory/access', headers=oh, json={
            'user_id': ids['stock_return_clerk'], 'can_prepare': False,
            'can_approve': False, 'reason': 'Synthetic immediate revocation of returns'}))
        assert clerk.post('/api/inventory/returns', headers=ch,
                          json={**payload, 'request_id': 'g3d_return_00005'}).status_code == 403
        print('PASS G3D independent source-lot partial returns, accurate net case FIFO cost, balanced GL, immutable documents, direct SQLite guard, revocation and month-close preflight')


if __name__ == '__main__':
    run()
