"""Chronological FIFO must not change already-posted newer valuation by backdating."""
import os
import sys
import tempfile
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'fifo.sqlite3'),
                          RAMSES_ADMIN_USER='owner', RAMSES_ADMIN_PASSWORD='g3c_synthetic_owner_password')
        for name in ('GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON'):
            os.environ.pop(name, None)
        from bootstrap import initialize, connect
        initialize()
        from app import app, stamp
        from inventory import fifo_allocate, ledger_post
        from fastapi.testclient import TestClient
        owner, clerk, reviewer = [TestClient(app) for _ in range(3)]

        def ok(resp):
            assert resp.status_code == 200, (resp.status_code, resp.text)
            return resp.json()

        def login(client, name, pw):
            return {'X-CSRF-Token': ok(client.post('/api/login', json={'username': name, 'password': pw}))['csrf']}

        oh = login(owner, 'owner', 'g3c_synthetic_owner_password')
        for name, role in (('g3c_fifo_clerk', 'clerk'), ('g3c_fifo_reviewer', 'reviewer')):
            ok(owner.post('/api/users', headers=oh, json={
                'username': name, 'role': role, 'password': 'g3c_synthetic_staff_password'}))
        ch = login(clerk, 'g3c_fifo_clerk', 'g3c_synthetic_staff_password')
        rh = login(reviewer, 'g3c_fifo_reviewer', 'g3c_synthetic_staff_password')
        users = {x['username']: x['id'] for x in ok(owner.get('/api/users'))}
        for name in ('g3c_fifo_clerk', 'g3c_fifo_reviewer'):
            ok(owner.post('/api/inventory/access', headers=oh, json={
                'user_id': users[name], 'can_prepare': name.endswith('clerk'),
                'can_approve': name.endswith('reviewer'),
                'reason': 'Synthetic chronological FIFO approval'}))
        reviewer_id = users['g3c_fifo_reviewer']
        day = datetime.now(ZoneInfo('Africa/Cairo')).date()
        later = day.isoformat()
        earlier = (day - timedelta(days=2)).isoformat()
        vendor = ok(owner.post('/api/inventory/vendors', headers=oh, json={
            'code': 'G3C_DATE_VENDOR', 'name': 'Synthetic FIFO chronology supplier'}))['id']
        item = ok(owner.post('/api/inventory/items', headers=oh, json={
            'code': 'G3C_DATE_ITEM', 'name': 'Synthetic FIFO chronology dressing'}))['id']
        dept = next(x['id'] for x in ok(owner.get('/api/lookups'))['departments'] if x['code'] == 'IPD')

        def receipt(seq, received, unit_cost='12.00', approve=True):
            rid = ok(clerk.post('/api/inventory/receipts', headers=ch, json={
                'vendor_id': vendor, 'received_on': received,
                'invoice_ref': f'G3C-SUPPLIER-CHRON-{seq}',
                'evidence_ref': f'G3C-SYNTH-RECEIPT-{seq}',
                'request_id': f'g3c_chron_receipt_{seq:04d}',
                'lines': [{'item_id': item, 'quantity': 3, 'unit_cost': unit_cost}]}))['id']
            if approve:
                ok(reviewer.post(f'/api/inventory/receipts/{rid}/decision', headers=rh, json={
                    'decision': 'approve', 'note': 'Independent synthetic FIFO receipt review'}))
            return rid

        def issue(seq, used, approve=True):
            iid = ok(clerk.post('/api/inventory/issues', headers=ch, json={
                'department_id': dept, 'used_on': used,
                'evidence_ref': f'G3C-SYNTH-ISSUE-{seq}',
                'request_id': f'g3c_chron_issue_{seq:04d}',
                'lines': [{'item_id': item, 'quantity': 1}]}))['id']
            if approve:
                ok(reviewer.post(f'/api/inventory/issues/{iid}/decision', headers=rh, json={
                    'decision': 'approve', 'note': 'Independent synthetic FIFO issue review'}))
            return iid

        receipt(1, earlier)
        issue(1, later)
        late_early_issue = issue(2, earlier, approve=False)
        late_early_receipt = receipt(2, earlier, unit_cost='3.00', approve=False)
        with connect() as c:
            before = (c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0],
                      c.execute('SELECT COUNT(*) FROM inventory_issue_allocations').fetchone()[0],
                      c.execute("SELECT COUNT(*) FROM inventory_receipts WHERE status='approved'").fetchone()[0])
        for path in (f'/api/inventory/issues/{late_early_issue}/decision',
                     f'/api/inventory/receipts/{late_early_receipt}/decision'):
            response = reviewer.post(path, headers=rh, json={
                'decision': 'approve', 'note': 'Cannot backdate after approved future FIFO issue'})
            assert response.status_code == 409, (path, response.status_code, response.text)
        with connect() as c:
            after = (c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0],
                     c.execute('SELECT COUNT(*) FROM inventory_issue_allocations').fetchone()[0],
                     c.execute("SELECT COUNT(*) FROM inventory_receipts WHERE status='approved'").fetchone()[0])
            assert before == after, (before, after)
            assert c.execute('SELECT status FROM inventory_issues WHERE id=?', (late_early_issue,)).fetchone()[0] == 'pending'
            assert c.execute('SELECT status FROM inventory_receipts WHERE id=?', (late_early_receipt,)).fetchone()[0] == 'pending'

            # A direct SQL approver cannot bypass API date ordering by creating a valid journal.
            c.execute('BEGIN IMMEDIATE')
            try:
                amount = 900
                jid = ledger_post(c, earlier, 'PURCHASE', late_early_receipt,
                                  users['g3c_fifo_clerk'], reviewer_id, '1100', '2200', amount)
                try:
                    c.execute("UPDATE inventory_receipts SET status='approved', reviewed_by=?, reviewed_at=?, review_note=?, journal_id=? WHERE id=?",
                              (reviewer_id, stamp(), 'Synthetic SQL bypass attempt', jid, late_early_receipt))
                except sqlite3.IntegrityError:
                    pass
                else:
                    raise AssertionError('A backdated receipt passed the SQLite approval trigger')
            finally:
                c.rollback()
            c.execute('BEGIN IMMEDIATE')
            try:
                record = c.execute('SELECT * FROM inventory_issues WHERE id=?', (late_early_issue,)).fetchone()
                cost = fifo_allocate(c, record)
                jid = ledger_post(c, earlier, 'CONSUMPTION', late_early_issue,
                                  users['g3c_fifo_clerk'], reviewer_id, '5100', '1100', cost, dept)
                try:
                    c.execute("UPDATE inventory_issues SET status='approved', reviewed_by=?, reviewed_at=?, review_note=?, cost_piasters=?, journal_id=? WHERE id=?",
                              (reviewer_id, stamp(), 'Synthetic SQL bypass attempt', cost, jid, late_early_issue))
                except sqlite3.IntegrityError:
                    pass
                else:
                    raise AssertionError('A backdated issue passed the SQLite approval trigger')
            finally:
                c.rollback()
        # Same-day approvals remain possible in the old day-resolution accounting model.
        issue(3, later)
        report = ok(owner.get('/api/inventory/reconciliation', params={'period': later[:7]}))
        assert report['matched'], report
        print('PASS G3C chronological FIFO: API and SQLite reject backdated approvals without partial GL; same-day allowed')


if __name__ == '__main__':
    run()
