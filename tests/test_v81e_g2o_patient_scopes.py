"""G2O regression: reviewer point grants for patient cases, receipts, credits and corrections.

Run against an isolated synthetic database: python3 tests/test_v81e_g2o_patient_scopes.py
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as d:
        os.environ['RAMSES_DB_PATH'] = str(Path(d) / 'scope.sqlite3')
        os.environ['RAMSES_ADMIN_USER'] = 'owner'
        os.environ['RAMSES_ADMIN_PASSWORD'] = 'owner_password_scoped_test_2026'
        from bootstrap import initialize, connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient

        owner, ext_reviewer, other_reviewer, cashier = (TestClient(app) for _ in range(4))

        def ok(resp, status=200):
            assert resp.status_code == status, (status, resp.status_code, resp.text)
            return resp.json() if status == 200 else None

        def login(client, name, password):
            return {'X-CSRF-Token': ok(client.post('/api/login', json={
                'username': name, 'password': password}))['csrf']}

        owner_headers = login(owner, 'owner', 'owner_password_scoped_test_2026')
        users = {}
        for name, role in [('ext_reviewer', 'reviewer'), ('other_reviewer', 'reviewer'),
                           ('cashier', 'clerk')]:
            users[name] = ok(owner.post('/api/users', headers=owner_headers, json={
                'username': name, 'role': role, 'password': 'staff_password_scoped_test_2026'}))['id']
        ext_headers = login(ext_reviewer, 'ext_reviewer', 'staff_password_scoped_test_2026')
        other_headers = login(other_reviewer, 'other_reviewer', 'staff_password_scoped_test_2026')
        cashier_headers = login(cashier, 'cashier', 'staff_password_scoped_test_2026')
        cfg = ok(owner.get('/api/billing/config'))
        external = next(p['id'] for p in cfg['points'] if p['kind'] == 'external')
        internal = next(p['id'] for p in cfg['points'] if p['kind'] == 'internal')
        day = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()

        def grant(user, point, active=True):
            return ok(owner.post(f'/api/billing/points/{point}/assign', headers=owner_headers,
                       json={'user_id': users[user], 'active': active}))

        grant('cashier', external)
        grant('ext_reviewer', external)
        assert ok(ext_reviewer.get('/api/billing/config'))['points'][0]['id'] == external
        assert ok(other_reviewer.get('/api/billing/config'))['points'] == []
        # Don't disclose payment clearing wallet identifiers to cashier/reviewer.
        if cfg['payment_channels']:
            assert 'fund_id' not in ok(cashier.get('/api/billing/config'))['payment_channels'][0]
        patients = {}
        cases = {}
        for kind, point in [('outpatient', external), ('inpatient', internal)]:
            patients[kind] = ok(owner.post('/api/billing/patients', headers=owner_headers, json={
                'display_name': f'Synthetic G2O patient {kind}',
                'request_id': f'g2o_patient_{kind}_12345678'}))
            cases[kind] = ok(owner.post('/api/billing/cases', headers=owner_headers, json={
                'patient_id': patients[kind]['id'], 'kind': kind,
                'point_id': point, 'business_date': day,
                'request_id': f'g2o_case_{kind}_123456789'}))['id']
        # Guessing an ID cannot reveal a patient in another point to the reviewer.
        ok(ext_reviewer.get(f"/api/billing/cases/{cases['inpatient']}"), 403)
        ok(ext_reviewer.get(f"/api/billing/cases/{cases['inpatient']}/finance"), 403)
        ok(ext_reviewer.get(f"/api/billing/cases/{cases['inpatient']}/adjustments"), 403)
        ok(other_reviewer.get(f"/api/billing/cases/{cases['outpatient']}"), 403)
        assert len(ok(ext_reviewer.get('/api/billing/cases'))['items']) == 1
        assert ok(other_reviewer.get('/api/billing/cases'))['items'] == []
        ok(other_reviewer.get('/api/billing/summary'), 403)
        ok(ext_reviewer.get('/api/billing/summary'), 403)
        ok(owner.get('/api/billing/summary'))
        assert ok(ext_reviewer.get('/api/billing/patients?q=Synthetic'))['items'][0]['id'] == patients['outpatient']['id']
        assert not ok(ext_reviewer.get('/api/billing/patients?q=Synthetic%20G2O%20patient%20inpatient'))['items']
        assert not ok(other_reviewer.get('/api/billing/patients?q=Synthetic'))['items']
        ok(ext_reviewer.get(f"/api/billing/cases/{cases['outpatient']}"))
        # Financial review decisions must use the same point scope as patient reads.
        dept = next(x['id'] for x in ok(owner.get('/api/lookups'))['departments'] if x['code'] == 'LAB')
        service = ok(owner.post('/api/billing/services', headers=owner_headers, json={
            'code': 'G2O_TEST_CLINIC', 'name': 'Synthetic medical service',
            'department_id': dept}))['id']
        ok(owner.post(f'/api/billing/services/{service}/prices', headers=owner_headers,
                      json={'valid_from': day, 'amount': '120'}))
        line = ok(owner.post(f"/api/billing/cases/{cases['outpatient']}/services", headers=owner_headers,
                             json={'service_id': service, 'quantity': 1,
                                   'request_id': 'g2o_line_outpatient_12345'}))['id']
        ok(owner.post(f'/api/billing/lines/{line}/fulfill', headers=owner_headers))
        draft = ok(owner.post(f"/api/billing/cases/{cases['outpatient']}/drafts", headers=owner_headers,
                              json={'request_id': 'g2o_draft_outpatient_12345'}))['id']
        invoice = ok(owner.post(f'/api/billing/drafts/{draft}/issue', headers=owner_headers,
                                json={'request_id': 'g2o_issue_outpatient_12345'}))['id']
        credit = ok(owner.post(f"/api/billing/cases/{cases['outpatient']}/credits", headers=owner_headers,
                               json={'invoice_id': invoice, 'amount': '10',
                                     'reason': 'Synthetic correction of invoice charge',
                                     'request_id': 'g2o_credit_outpatient_12345'}))['id']
        ok(other_reviewer.post(f'/api/billing/credits/{credit}/decision', headers=other_headers,
                               json={'decision': 'reject', 'note': 'No point assignment'}), 403)
        # A read-scoped reviewer may reject the request without editing the GL.
        ok(ext_reviewer.post(f'/api/billing/credits/{credit}/decision', headers=ext_headers,
                             json={'decision': 'reject', 'note': 'Synthetic evidence rejected'}))
        # An arbitrary refund record in this case cannot be approved from another station.
        with connect() as c:
            required = c.execute('PRAGMA table_info(billing_refund_requests)').fetchall()
            cols = {r['name'] for r in required if r['notnull'] and r['dflt_value'] is None and not r['pk']}
            fields = {
                'refund_no': 'RF-G2O-TEST', 'case_id': cases['outpatient'], 'point_id': external,
                'source': 'credit', 'method': 'cash', 'amount_piasters': 1000,
                'reason': 'Synthetic refund needing independent review',
                'requested_by': users['cashier'], 'requested_at': datetime.now().isoformat(),
            }
            assert cols <= fields.keys(), cols - fields.keys()
            cur = c.execute('INSERT INTO billing_refund_requests (' + ','.join(fields) + ') VALUES (' +
                            ','.join('?' * len(fields)) + ')', tuple(fields.values()))
            refund = cur.lastrowid
        ok(other_reviewer.post(f'/api/billing/refunds/{refund}/decision', headers=other_headers,
                               json={'decision': 'reject'}), 403)
        ok(ext_reviewer.post(f'/api/billing/refunds/{refund}/decision', headers=ext_headers,
                             json={'decision': 'reject'}))
        # Patient correction events have potentially identifying narratives.
        ticket = ok(cashier.post('/api/corrections', headers=cashier_headers, json={
            'source_type': 'invoice', 'source_id': invoice, 'issue_type': 'wrong_amount',
            'reason': 'Synthetic patient invoice contains incorrect item price',
            'proposed_resolution': 'Investigate signed pricing evidence carefully',
            'request_key': 'g2o_correction_open_1234'}))['id']
        assert [r['id'] for r in ok(ext_reviewer.get('/api/corrections'))['tickets']] == [ticket]
        assert ok(other_reviewer.get('/api/corrections'))['tickets'] == []
        ok(other_reviewer.get(f'/api/corrections/{ticket}/history'), 403)
        ok(other_reviewer.post(f'/api/corrections/{ticket}/review', headers=other_headers,
                               json={'decision': 'triage', 'note': 'Unauthorized correction review'}), 403)
        ok(ext_reviewer.get(f'/api/corrections/{ticket}/history'))
        # Historical paper incidents also contain custodian details; reviewers
        # must not enumerate incidents across stations after being scoped.
        with connect() as c:
            import cashier_ops
            slot = cashier_ops.slots_for(c, external, day)[0]['code']
        incident = ok(cashier.post('/api/late-entries', headers=cashier_headers, json={
            'request_key': 'g2o_incident_created_1234', 'point_id': external,
            'business_date': day, 'shift_code': slot, 'incident_reason': 'outage',
            'custodian_name': 'Synthetic receptionist', 'cash_location': 'drawer',
            'note': 'Synthetic incident, no genuine money or medical records'}))['id']
        assert [x['id'] for x in ok(ext_reviewer.get('/api/late-entries'))['items']] == [incident]
        assert ok(other_reviewer.get('/api/late-entries'))['items'] == []
        ok(other_reviewer.get(f'/api/late-entries/{incident}'), 403)
        ok(ext_reviewer.get(f'/api/late-entries/{incident}'))
        # Revoke while session is live and verify *all* direct read/write accesses fail.
        grant('ext_reviewer', external, active=False)
        assert ok(ext_reviewer.get('/api/billing/config'))['points'] == []
        ok(ext_reviewer.get(f"/api/billing/cases/{cases['outpatient']}"), 403)
        ok(ext_reviewer.get(f'/api/corrections/{ticket}/history'), 403)
        ok(ext_reviewer.get(f'/api/late-entries/{incident}'), 403)
        assert ok(ext_reviewer.get('/api/late-entries'))['items'] == []
        ok(ext_reviewer.post(f'/api/corrections/{ticket}/review', headers=ext_headers,
                             json={'decision': 'triage', 'note': 'Revoked user review attempt'}), 403)
        assert ok(ext_reviewer.get('/api/corrections'))['tickets'] == []
        # Grant internal point only, while external remains denied.
        grant('ext_reviewer', internal)
        ok(ext_reviewer.get(f"/api/billing/cases/{cases['inpatient']}"))
        ok(ext_reviewer.get(f"/api/billing/cases/{cases['outpatient']}"), 403)
        with connect() as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        print('PASS G2O patient reviewer point grants, credit/refund/correction IDOR and instant revocation')


if __name__ == '__main__':
    run()
