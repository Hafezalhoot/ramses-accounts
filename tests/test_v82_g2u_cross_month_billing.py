"""G2U: sealed admission month must not block billing newly performed services."""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'test.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_g2u_owner_password')
        from bootstrap import initialize, connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner, clerk, reviewer = (TestClient(app) for _ in range(3))

        def ok(response, status=200):
            assert response.status_code == status, (response.status_code, response.text, status)
            return response.json() if status == 200 else None

        def login(client, name, password):
            return {'X-CSRF-Token': ok(client.post('/api/login', json={
                'username': name, 'password': password}))['csrf']}

        oh = login(owner, 'owner', 'synthetic_g2u_owner_password')
        people = {}
        for name, role in [('g2u_clerk', 'clerk'), ('g2u_reviewer', 'reviewer')]:
            people[name] = ok(owner.post('/api/users', headers=oh, json={
                'username': name, 'role': role, 'password': 'synthetic_g2u_staff_password'}))['id']
        ch = login(clerk, 'g2u_clerk', 'synthetic_g2u_staff_password')
        rh = login(reviewer, 'g2u_reviewer', 'synthetic_g2u_staff_password')
        point = next(p['id'] for p in ok(owner.get('/api/billing/config'))['points'] if p['kind'] == 'internal')
        for person in people.values():
            ok(owner.post(f'/api/billing/points/{point}/assign', headers=oh,
                          json={'user_id': person, 'active': True}))

        today = datetime.now(ZoneInfo('Africa/Cairo')).date()
        # On the first day of a month no current-month night has completed.
        # Simulate day 3 in the SAME month, with the new API/bed clock only.
        if today.day == 1:
            today = today + timedelta(days=2)
            import billing, bed_stays
            billing.cairo_today = lambda: today.isoformat()
            bed_stays.cairo_today = lambda: today.isoformat()
        previous_day = today.replace(day=1) - timedelta(days=1)
        old_period = previous_day.strftime('%Y-%m')
        current_period = today.strftime('%Y-%m')
        department = next(x['id'] for x in ok(owner.get('/api/lookups'))['departments'] if x['code'] == 'IPD')
        service = ok(owner.post('/api/billing/services', headers=oh, json={
            'code': 'G2U_NIGHT', 'name': 'Synthetic new-month bed night',
            'department_id': department}))['id']
        ok(owner.post(f'/api/billing/services/{service}/prices', headers=oh, json={
            'valid_from': previous_day.isoformat(), 'amount': '100'}))
        ok(owner.post(f'/api/billing/services/{service}/prices', headers=oh, json={
            'valid_from': today.replace(day=1).isoformat(), 'amount': '125'}))
        bed = ok(owner.post('/api/beds/catalog', headers=oh, json={
            'code': 'G2U_BED', 'name': 'Synthetic G2U bed', 'kind': 'inpatient',
            'service_id': service}))['id']
        patient = ok(clerk.post('/api/billing/patients', headers=ch, json={
            'display_name': 'Synthetic cross month resident',
            'request_id': 'g2u_patient_xmonth_01'}))['id']
        case = ok(clerk.post('/api/billing/cases', headers=ch, json={
            'patient_id': patient, 'point_id': point, 'kind': 'inpatient',
            'business_date': previous_day.isoformat(),
            'request_id': 'g2u_case_xmonth_0001'}))['id']
        stay = ok(owner.post(f'/api/beds/cases/{case}/admit', headers=oh, json={
            'bed_id': bed, 'start_date': (today - timedelta(days=1)).isoformat(),
            'evidence_reference': 'SYN-G2U-CURRENT-ADMISSION',
            'request_id': 'g2u_stay_xmonth_0001'}))['id']
        with connect() as c:
            c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES (?,?,?)',
                      (old_period, 1, today.isoformat()))
            c.commit()
        charge = ok(owner.post(f'/api/beds/stays/{stay}/charge', headers=oh,
                               json={'through_date': today.isoformat(),
                                     'request_id': 'g2u_night_xmonth_0001'}))
        assert charge['created_nights'] == 1 and charge['total_piasters'] == 12500, charge
        line = ok(owner.get(f'/api/billing/cases/{case}'))['services'][0]
        ok(reviewer.post(f'/api/billing/lines/{line["id"]}/fulfill', headers=rh))
        draft = ok(clerk.post(f'/api/billing/cases/{case}/drafts', headers=ch,
                              json={'request_id': 'g2u_draft_xmonth_0001'}))
        assert draft['total_piasters'] == 12500, draft
        invoice = ok(clerk.post(f'/api/billing/drafts/{draft["id"]}/issue', headers=ch,
                                json={'request_id': 'g2u_invoice_xmonth_001'}))
        with connect() as c:
            row = c.execute('''SELECT i.issued_date,j.entry_date,j.status, i.total_piasters
                 FROM billing_invoices i JOIN gl_journals j ON j.id=i.journal_id
                 WHERE i.id=?''', (invoice['id'],)).fetchone()
            assert row['issued_date'] == today.isoformat() and row['entry_date'] == today.isoformat(), dict(row)
            assert row['status'] == 'posted' and row['total_piasters'] == 12500, dict(row)
            assert c.execute('SELECT COUNT(*) FROM periods WHERE period=?', (old_period,)).fetchone()[0] == 1
            assert c.execute('SELECT COUNT(*) FROM gl_journals WHERE substr(entry_date,1,7)=?',
                             (old_period,)).fetchone()[0] == 0
        # A second, non-bed service belongs to the current accounting period.
        # A stale admission-month filter must NOT let October close with it unbilled.
        lab = ok(owner.post('/api/billing/services', headers=oh, json={
            'code': 'G2U_LAB', 'name': 'Synthetic pending October service',
            'department_id': department}))['id']
        ok(owner.post(f'/api/billing/services/{lab}/prices', headers=oh, json={
            'valid_from': today.replace(day=1).isoformat(), 'amount': '45'}))
        pending_line = ok(clerk.post(f'/api/billing/cases/{case}/services', headers=ch, json={
            'service_id': lab, 'quantity': 1,
            'request_id': 'g2u_service_pending_line_01'}))['id']
        ok(reviewer.post(f'/api/billing/lines/{pending_line}/fulfill', headers=rh))
        with connect() as c:
            row = c.execute('SELECT service_date,unit_price_piasters FROM billing_case_lines WHERE id=?',
                            (pending_line,)).fetchone()
            assert (row['service_date'],row['unit_price_piasters']) == (today.isoformat(),4500),dict(row)
            # Once clinically fulfilled, financial source facts must not be rewritable.
            import sqlite3
            try:
                c.execute('UPDATE billing_case_lines SET service_date=? WHERE id=?',
                          (previous_day.isoformat(),pending_line))
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError('Fulfilled service date was mutable after attestation')
        # Administratively release the synthetic bed to avoid other unfinished nights.
        ok(owner.post(f'/api/beds/stays/{stay}/release', headers=oh, json={
            'end_date': today.isoformat(),
            'evidence_reference': 'SYN-G2U-BED-RELEASE-EVIDENCE'}))
        preflight = ok(owner.get('/api/periods/preflight', params={'period': current_period}))
        assert not preflight['ready'] and 'خدمات مرضى منفذة لم تُفوتر' in preflight['reason'], preflight
        # GL coverage must count the draft against the SERVICE period, not admission.
        second_draft=ok(clerk.post(f'/api/billing/cases/{case}/drafts',headers=ch,
                                   json={'request_id':'g2u_october_unissued_draft_01'}))
        assert second_draft['total_piasters']==4500
        old_cover=ok(owner.get('/api/accounting/trial-balance',params={'period':old_period}))['coverage']
        current_cover=ok(owner.get('/api/accounting/trial-balance',params={'period':current_period}))['coverage']
        assert old_cover['unissued_drafts']==0,old_cover
        assert current_cover['unissued_drafts']==1,current_cover
        print(f'PASS G2U: old closed {old_period} does not block {current_period} invoicing/GL, closing and coverage')

if __name__ == '__main__':
    run()
