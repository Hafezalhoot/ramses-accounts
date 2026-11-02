"""S4: one disposable SQLite database linking patient, till, supplier and bank.

All amounts and identities are fictional. The only clock patch happens at the
final month-end test gate, never in the API/application or real operation.
"""
import io
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s4-single-db-') as root:
        os.environ.update(RAMSES_DB_PATH=str(Path(root) / 's4.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='s4_owner_synthetic_local_password',
                          RAMSES_ENVIRONMENT='staging')
        for key in ('GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_ID',
                    'GOOGLE_SHEET_TARGET', 'RAMSES_REQUIRE_PAYMENT_EVIDENCE'):
            os.environ.pop(key, None)
        from bootstrap import initialize, connect
        from app import app
        from fastapi.testclient import TestClient
        use_http = os.getenv('S4_REAL_HTTP') == '1'
        if use_http:
            from s3_http_transport import RemoteTestClient as TestClient
        import billing
        import ledger
        initialize()
        actors = ('owner', 'night', 'morning', 'evening', 'treasury', 'reviewer',
                  'buyer', 'store_reviewer', 'pay_maker', 'pay_approver',
                  'bank_maker', 'bank_reviewer', 'outsider')
        clients = {who: TestClient(app) for who in actors}

        def ok(resp, status=200):
            assert resp.status_code == status, (status, resp.status_code, resp.text[:900])
            return resp.json() if status == 200 else None

        def api(who, method, path, body=None, *, params=None, **kw):
            return clients[who].request(method, path, json=body,
                                        headers=headers[who], params=params, **kw)

        headers = {}
        headers['owner'] = {'X-CSRF-Token': ok(clients['owner'].post('/api/login', json={
            'username': 'owner', 'password': 's4_owner_synthetic_local_password'}))['csrf']}
        for who in actors[1:]:
            role = 'reviewer' if who in ('reviewer', 'store_reviewer', 'pay_approver', 'bank_reviewer') else 'clerk'
            ok(api('owner', 'POST', '/api/users', {'username': who, 'role': role,
                            'password': 's4_staff_synthetic_local_password'}))
            headers[who] = {'X-CSRF-Token': ok(clients[who].post('/api/login', json={
                'username': who, 'password': 's4_staff_synthetic_local_password'}))['csrf']}
        ids = {row['username']: row['id'] for row in ok(api('owner', 'GET', '/api/users'))}
        today = datetime.now(ZoneInfo('Africa/Cairo')).date()
        day = today.isoformat()
        prior_last = (today.replace(day=1) - timedelta(days=1)).isoformat()
        month = day[:7]
        tomorrow = (today + timedelta(days=1)).isoformat()
        look = ok(api('owner', 'GET', '/api/lookups'))
        fund = {x['code']: x['id'] for x in look['funds']}
        depts = {x['code']: x['id'] for x in look['departments']}
        cats = {x['code']: x['id'] for x in look['categories']}
        main, sub, bank = fund['cash_main'], fund['cash_sub'], fund['bank']
        points = ok(api('owner', 'GET', '/api/cashier/plans'))['points']
        ext = next(x for x in points if x['kind'] == 'external')['id']
        inner = next(x for x in points if x['kind'] == 'internal')['id']
        for point_id, fund_id in ((ext, sub), (inner, main)):
            ok(api('owner', 'POST', f'/api/billing/points/{point_id}/cash-fund', {'fund_id': fund_id}))
        for who in ('night', 'morning', 'evening', 'treasury'):
            ok(api('owner', 'POST', f'/api/billing/points/{ext}/assign', {'user_id': ids[who]}))
        ok(api('owner', 'POST', f'/api/billing/points/{inner}/assign', {'user_id': ids['treasury']}))
        from reviewer_scope_helpers import grant_reviewers_for_test
        grant_reviewers_for_test(clients['owner'], headers['owner'])

        # Test fixture only: the simulated hospital was commissioned today.
        # The operational month has exactly one required station day, and a
        # historical internal station snapshot for the closed-paper envelope.
        with connect() as c:
            c.execute('UPDATE cashier_schedule_versions SET starts_on=? WHERE point_id=?', (prior_last, inner))
            c.execute('UPDATE cashier_point_lifecycle SET starts_on=? WHERE point_id=?', (prior_last, inner))
            if today.day > 1:
                c.execute('INSERT INTO cashier_point_lifecycle(point_id,starts_on,enabled) VALUES (?,?,0)',
                          (inner, today.strftime('%Y-%m-01')))
            c.execute('INSERT INTO cashier_point_lifecycle(point_id,starts_on,enabled) VALUES (?,?,1)',
                      (inner, day))
            for point_id in (ext, inner):
                c.execute('INSERT INTO cashier_point_lifecycle(point_id,starts_on,enabled) VALUES (?,?,0)',
                          (point_id, tomorrow))
            c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES (?,?,?)',
                      (prior_last[:7], ids['owner'], datetime.now(ZoneInfo('UTC')).isoformat()))
        # One prior period is synthetic closed evidence, NOT a replay of V8.0.
        central = ok(api('treasury', 'POST', '/api/shifts/open', {
            'fund_id': main, 'business_date': day, 'shift': 'treasury'}))['id']

        # Actual patient invoice and cash collection form the 100 EGP night receipt.
        service = ok(api('owner', 'POST', '/api/billing/services', {
            'code': 'S4_CASH_LAB', 'name': 'Fictional nonclinical test',
            'department_id': depts['LAB'], 'suggested_point': 'external'}))['id']
        ok(api('owner', 'POST', f'/api/billing/services/{service}/prices',
               {'valid_from': day, 'amount': '100.00'}))
        shift_ids = []
        for who, amount in (('night', 100), ('morning', 200), ('evening', 300)):
            sid = ok(api(who, 'POST', '/api/shifts/open', {
                'fund_id': sub, 'business_date': day, 'shift': who}))['id']
            shift_ids.append(sid)
            if who == 'night':
                patient = ok(api(who, 'POST', '/api/billing/patients', {
                    'display_name': 'S4 Synthetic No Patient Data',
                    'request_id': 's4_patient_registration_0001'}))
                case = ok(api(who, 'POST', '/api/billing/cases', {
                    'patient_id': patient['id'], 'kind': 'outpatient', 'point_id': ext,
                    'business_date': day, 'request_id': 's4_patient_case_0001'}))
                line = ok(api(who, 'POST', f'/api/billing/cases/{case["id"]}/services', {
                    'service_id': service, 'quantity': 1,
                    'request_id': 's4_patient_service_0001'}))['id']
                ok(api('reviewer', 'POST', f'/api/billing/lines/{line}/fulfill'))
                draft = ok(api(who, 'POST', f'/api/billing/cases/{case["id"]}/drafts', {
                    'request_id': 's4_invoice_draft_0001'}))['id']
                invoice = ok(api(who, 'POST', f'/api/billing/drafts/{draft}/issue', {
                    'request_id': 's4_invoice_issue_0001'}))['id']
                collection = {'point_id': ext, 'invoice_id': invoice,
                              'parts': [{'method': 'cash', 'amount': '100'}],
                              'request_id': 's4_cash_collection_0001'}
                ok(api(who, 'POST', f'/api/billing/cases/{case["id"]}/collect', collection))
                assert ok(api(who, 'POST', f'/api/billing/cases/{case["id"]}/collect', collection))['replayed']
                assert ok(api(who, 'GET', f'/api/billing/cases/{case["id"]}/finance'))['outstanding_piasters'] == 0
            else:
                voucher = ok(api(who, 'POST', '/api/vouchers', {
                    'date': day, 'kind': 'receipt', 'shift': who, 'from_fund_id': sub,
                    'department_id': depts['CLINIC'], 'category_id': cats['medical_revenue'],
                    'amount': str(amount), 'description': 'Synthetic shift receipt'}))['id']
                ok(api('reviewer', 'POST', f'/api/vouchers/{voucher}/decision', {'decision': 'approve'}))
            ok(api(who, 'POST', f'/api/shifts/{sid}/count', {
                'counted_amount': str(amount), 'note': 'S4 independently counted till'}))
            assert api(who, 'POST', f'/api/shifts/{sid}/handoff',
                       {'counted_amount': str(amount), 'decision': 'accept'}).status_code == 403
            ok(api('treasury', 'POST', f'/api/shifts/{sid}/handoff', {
                'counted_amount': str(amount), 'decision': 'accept', 'note': 'S4 independent till custody'}))
            assert api(who, 'POST', '/api/cashier/treasury-deposits', {
                'source_shift_id': sid, 'amount': str(amount),
                'note': f'S4 source sealed {who}'}).status_code == 403
            ok(api('treasury', 'POST', '/api/cashier/treasury-deposits', {
                'source_shift_id': sid, 'amount': str(amount),
                'note': f'S4 source sealed {who}', 'client_request_id': f's4_treasury_deposit_{who}_0001'}))
            assert api('treasury', 'POST', '/api/cashier/treasury-deposits', {
                'source_shift_id': sid, 'amount': str(amount),
                'note': f'S4 changed source sealed {who}', 'client_request_id': f's4_treasury_deposit_{who}_0001'}).status_code == 409
            ok(api('reviewer', 'POST', f'/api/shifts/{sid}/review', {'decision': 'approve'}))

        # Physical cash expense from central till; only independent reviewer posts.
        voucher = ok(api('treasury', 'POST', '/api/vouchers', {
            'date': day, 'kind': 'payment', 'shift': 'central', 'from_fund_id': main,
            'department_id': depts['ADMIN'], 'category_id': cats['utilities'],
            'amount': '50', 'description': 'Synthetic central cash expense'}))['id']
        ok(api('reviewer', 'POST', f'/api/vouchers/{voucher}/decision', {'decision': 'approve'}))
        with connect() as c:
            assert billing.invoice_due(c, invoice) == 0
            assert c.execute('SELECT COUNT(*) FROM cashier_treasury_transfers').fetchone()[0] == 3
        print('S4_CHECKPOINT patient cash 100 + other cash 500; source transfers 600, central expense 50', flush=True)
        # Supplier document chain uses distinct warehouse/accounting approvers.
        for who, prepare, approve in (
            ('buyer', True, False), ('store_reviewer', False, True),
            ('pay_maker', True, False), ('pay_approver', False, True),
            ('bank_maker', True, False)):
            ok(api('owner', 'POST', '/api/inventory/access', {
                'user_id': ids[who], 'can_prepare': prepare, 'can_approve': approve,
                'reason': 'S4 synthetic independent inventory and AP source'}))
        vendor = ok(api('owner', 'POST', '/api/inventory/vendors', {
            'code': 'S4-VENDOR', 'name': 'Synthetic nonclinical vendor'}))['id']
        item = ok(api('owner', 'POST', '/api/inventory/items', {
            'code': 'S4-GAUZE', 'name': 'Synthetic nondrug gauze', 'unit': 'piece'}))['id']
        po = ok(api('buyer', 'POST', '/api/inventory/purchase-orders', {
            'vendor_id': vendor, 'ordered_on': day, 'order_ref': 'S4-PO-01',
            'evidence_ref': 'S4-SYNTH-ORDER-REF', 'request_id': 's4_po_document_0001',
            'lines': [{'item_id': item, 'quantity': 10, 'unit_cost': '10.00'}]}))['id']
        ok(api('store_reviewer', 'POST', f'/api/inventory/purchase-orders/{po}/decision',
               {'decision': 'approve', 'note': 'S4 independent synthetic PO approval'}))
        grn = ok(api('buyer', 'POST', '/api/inventory/receipts', {
            'vendor_id': vendor, 'received_on': day, 'purchase_order_id': po,
            'invoice_ref': 'S4-SUPPLIER-INVOICE', 'evidence_ref': 'S4-SYNTH-GRN-001',
            'request_id': 's4_supplier_receipt_0001',
            'lines': [{'item_id': item, 'quantity': 10, 'unit_cost': '10.00'}]}))['id']
        ok(api('store_reviewer', 'POST', f'/api/inventory/receipts/{grn}/decision',
               {'decision': 'approve', 'note': 'S4 stock received independently'}))
        inv = ok(api('buyer', 'POST', '/api/inventory/supplier-invoices', {
            'receipt_id': grn, 'invoice_date': day, 'invoice_ref': 'S4-SUPPLIER-INVOICE',
            'amount': '100.00', 'evidence_ref': 'S4-SYNTH-INVOICE-PDF',
            'request_id': 's4_vendor_invoice_0001',
            'lines': [{'item_id': item, 'quantity': 10, 'unit_cost': '10.00'}]}))['id']
        ok(api('store_reviewer', 'POST', f'/api/inventory/supplier-invoices/{inv}/decision',
               {'decision': 'approve', 'note': 'S4 independent three-document match'}))
        due = ok(api('buyer', 'POST', '/api/inventory/supplier-due-schedules', {
            'invoice_match_id': inv, 'scheduled_on': day, 'terms_ref': 'S4-NET-30',
            'request_id': 's4_vendor_due_0001',
            'lines': [{'due_on': (today + timedelta(days=30)).isoformat(), 'amount': '100.00'}]}))['id']
        ok(api('store_reviewer', 'POST', f'/api/inventory/supplier-due-schedules/{due}/decision',
               {'decision': 'approve', 'note': 'S4 independently signed due schedule'}))
        with connect() as c:
            due_line = c.execute('SELECT id FROM inventory_supplier_due_lines WHERE schedule_id=?',
                                 (due,)).fetchone()[0]
        request_id = ok(api('pay_maker', 'POST', '/api/inventory/supplier-payment-requests', {
            'due_line_id': due_line, 'requested_on': day, 'amount': '60.00',
            'evidence_ref': 'S4-APPROVED-PAYMENT-INTENT',
            'request_id': 's4_supplier_payment_intent_0001'}))['id']
        ok(api('pay_approver', 'POST', f'/api/inventory/supplier-payment-requests/{request_id}/decision',
               {'decision': 'approve', 'note': 'S4 independent payment intent approval'}))
        ok(api('owner', 'POST', f'/api/funds/{bank}/opening', {'amount': '200.00'}))
        for who, grant in [('bank_maker', 'can_submit'), ('bank_reviewer', 'can_approve')]:
            ok(api('owner', 'POST', '/api/fund-access', {
                'user_id': ids[who], 'fund_id': bank, grant: True,
                'reason': 'S4 independent synthetic bank authorizations'}))
        booked = ok(api('bank_maker', 'POST',
                        f'/api/inventory/supplier-payment-requests/{request_id}/bank-voucher', {
            'booked_on': day, 'bank_fund_id': bank, 'bank_reference': 'S4-BANK-PAY-0001',
            'request_id': 's4_bank_supplier_voucher_0001'}))
        bank_voucher = booked['voucher_id']
        assert api('pay_approver', 'POST', f'/api/vouchers/{bank_voucher}/decision',
                   {'decision': 'approve', 'reason': 'Not the independent bank approver'}).status_code == 403
        ok(api('bank_reviewer', 'POST', f'/api/vouchers/{bank_voucher}/decision',
               {'decision': 'approve', 'reason': 'S4 independent AP voucher posting'}))
        ledger_2200 = ok(api('owner', 'GET', '/api/inventory/supplier-control-ledger',
                             params={'as_of': day}))
        assert ledger_2200['control_2200_piasters'] == 4000, ledger_2200
        assert ledger_2200['attributed_2200_piasters'] == 4000, ledger_2200
        assert ledger_2200['unattributed_2200_piasters'] == 0 and ledger_2200['reconciled']
        assert ledger_2200['vendors'][0]['balance_piasters'] == 4000

        assert api('owner', 'POST', '/api/periods/close', {'period': month}).status_code == 409
        raw = (f'date,amount,description,reference\n{day},-60.00,S4 supplier,S4-BANK-PAY-0001\n').encode()
        batch = ok(api('owner', 'POST', '/api/bank-reconciliation/import', data={
            'fund_id': str(bank), 'period': month,
            'opening_balance': '200.00', 'closing_balance': '140.00'},
            files={'file': ('s4-bank.csv', io.BytesIO(raw), 'text/csv')}))['batch_id']
        candidate = ok(api('owner', 'GET', '/api/bank-reconciliation',
                           params={'period': month, 'fund_id': bank}))
        assert candidate['unmatched_bank_count'] == 1, candidate
        assert len(candidate['unmatched_ledger']) == 1, candidate
        ok(api('owner', 'POST', f'/api/bank-reconciliation/{batch}/match', {
            'line_id': candidate['lines'][0]['id'],
            'movement_id': candidate['unmatched_ledger'][0]['movement_id'],
            'note': 'S4 actual synthetic bank statement line matched'}))
        ok(api('owner', 'POST', '/api/fund-access', {
            'user_id': ids['bank_reviewer'], 'fund_id': bank,
            'can_submit': True, 'reason': 'S4 synthetic statement reviewer scope'}))
        settlements = ok(api('owner', 'GET', '/api/inventory/supplier-settlements'))
        assert settlements['supplier_booked_piasters'] == 6000
        assert settlements['bank_confirmed_piasters'] == 0  # matched is not approved
        print('S4_CHECKPOINT supplier GRN 100, 60 booked, statement still awaiting independent signoff', flush=True)
        # A PREVIOUSLY SEALED paper-only envelope is corrected in the current
        # period, without pretending its patient cash was collected a second time.
        with connect() as c:
            old_gl = [tuple(row) for row in c.execute('SELECT id,entry_date,status FROM gl_journals WHERE substr(entry_date,1,7)=? ORDER BY id', (prior_last[:7],))]
            old_cash = [tuple(row) for row in c.execute('SELECT id,booked_on,amount_piasters FROM fund_movements WHERE substr(booked_on,1,7)=? ORDER BY id', (prior_last[:7],))]
        old_service = ok(api('owner', 'POST', '/api/billing/services', {
            'code': 'S4_OLD_INPATIENT', 'name': 'Synthetic old nonclinical service',
            'department_id': depts['CLINIC'], 'suggested_point': 'either'}))['id']
        ok(api('owner', 'POST', f'/api/billing/services/{old_service}/prices',
               {'valid_from': prior_last, 'amount': '500.00'}))
        incident = ok(api('owner', 'POST', '/api/late-entries', {
            'request_key': 's4_paper_incident_000001', 'point_id': inner,
            'business_date': prior_last, 'shift_code': 'treasury',
            'incident_reason': 'absence', 'custodian_name': 'S4 fictional envelope custodian',
            'cash_location': 'main_safe', 'counted_cash': '1300',
            'source_register_ref': 'S4-CLOSED-OLD-ENV-01',
            'note': 'Synthetic paper receipt and petty expense'}))['id']
        document = ok(api('owner', 'POST', f'/api/late-entries/{incident}/documents', {
            'paper_ref': 'S4-OLD-PAT-01', 'kind': 'patient_receipt',
            'method': 'cash', 'amount': '1500.00'}))['id']
        expense_document = ok(api('owner', 'POST', f'/api/late-entries/{incident}/documents', {
            'paper_ref': 'S4-OLD-EXP-01', 'kind': 'expense', 'method': 'cash',
            'amount': '200.00', 'note': 'S4 original cash-paid supplies'}))['id']
        evidence = clients['owner'].post(f'/api/late-entries/{incident}/evidence',
                            headers=headers['owner'], files={'file': ('s4-count.png',
                            b'\x89PNG\r\n\x1a\nSYNTHETIC-NO-PATIENT-DATA', 'image/png')})
        ok(evidence)
        ok(api('owner', 'POST', f'/api/late-entries/{incident}/action', {
            'action': 'submit', 'note': 'S4 synthetic evidence ready for reviewer'}))
        ok(api('reviewer', 'POST', f'/api/late-entries/{incident}/action', {
            'action': 'triage', 'note': 'S4 independent paper source review'}))
        old_patient = ok(api('owner', 'POST', '/api/billing/patients', {
            'display_name': 'S4 Fake Historical Patient',
            'request_id': 's4_old_patient_record_00001'}))['code']
        recovered = ok(api('owner', 'POST',
                           f'/api/late-entries/{incident}/documents/{document}/recover-case', {
            'request_id': 's4_recover_old_case_000001', 'patient_code': old_patient,
            'kind': 'inpatient', 'note': 'Verified synthetic historical service'}))
        old_case = recovered['id']
        old_line = ok(api('owner', 'POST', f'/api/billing/cases/{old_case}/services', {
            'service_id': old_service, 'quantity': 3,
            'request_id': 's4_old_three_services_00001'}))['id']
        ok(api('reviewer', 'POST', f'/api/billing/lines/{old_line}/fulfill'))
        draft = ok(api('owner', 'POST', f'/api/billing/cases/{old_case}/drafts', {
            'request_id': 's4_old_draft_00001'}))['id']
        old_invoice = ok(api('owner', 'POST', f'/api/billing/drafts/{draft}/issue', {
            'request_id': 's4_old_invoice_issue_0001'}))['id']
        old_receipt = ok(api('owner', 'POST', '/api/vouchers', {
            'date': day, 'kind': 'receipt', 'department_id': depts['ADMIN'],
            'category_id': cats['late_cash_unallocated'], 'from_fund_id': main,
            'shift': 'central', 'amount': '1300.00',
            'description': 'Synthetic legacy physical envelope to main safe',
            'reference_no': 'S4-CLOSED-OLD-ENV-01',
            'client_request_id': 's4_original_old_envelope_0001'}))['id']
        ok(api('reviewer', 'POST', f'/api/vouchers/{old_receipt}/decision', {
            'decision': 'approve', 'reason': 'S4 verified physical old envelope'}))
        clear_body = {
            'request_id': 's4_old_mixed_settlement_00001', 'voucher_id': old_receipt,
            'patients': [{'document_id': document, 'invoice_id': old_invoice}],
            'expenses': [{'document_id': expense_document, 'category_code': 'hospitality',
                          'department_id': depts['ADMIN']}],
            'approve_variance': False, 'note': 'S4 independently cleared synthetic historical case'}
        with connect() as c:
            cash_count = c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
        cleared = ok(api('reviewer', 'POST', f'/api/late-entries/{incident}/clear-mixed-envelope', clear_body))
        assert cleared['variance_piasters'] == 0 and cleared['cash_newly_booked_piasters'] == 0, cleared
        assert ok(api('reviewer', 'POST', f'/api/late-entries/{incident}/clear-mixed-envelope', clear_body))['replayed']
        ok(api('reviewer', 'POST', f'/api/late-entries/{incident}/action', {
            'action': 'resolve', 'note': 'S4 cleared and independently reconciled'}))
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0] == cash_count
            assert billing.invoice_due(c, old_invoice) == 0
            assert old_gl == [tuple(row) for row in c.execute('SELECT id,entry_date,status FROM gl_journals WHERE substr(entry_date,1,7)=? ORDER BY id', (prior_last[:7],))]
            assert old_cash == [tuple(row) for row in c.execute('SELECT id,booked_on,amount_piasters FROM fund_movements WHERE substr(booked_on,1,7)=? ORDER BY id', (prior_last[:7],))]
        print('S4_CHECKPOINT historical invoice 1500, paper cash 1300, expense 200; no duplicate cash or prior-period rewrite', flush=True)
        # Month close sees custody and source-ledger controls, not just GL totals.
        assert api('outsider', 'GET', '/api/accounting/treasury-reconciliation',
                   params={'period': month}).status_code == 403
        assert api('outsider', 'GET', '/api/inventory/supplier-control-ledger',
                   params={'as_of': day}).status_code == 403
        assert api('outsider', 'GET', '/api/periods/preflight',
                   params={'period': month}).status_code == 403
        assert not ok(api('owner', 'GET', '/api/periods/preflight',
                          params={'period': month}))['ready']
        count = ok(api('treasury', 'POST', f'/api/shifts/{central}/count', {
            'counted_amount': '1850.00', 'note': 'S4 central net count'}))
        assert count['variance_piasters'] == 0, count
        ok(api('owner', 'POST', f'/api/shifts/{central}/handoff', {
            'counted_amount': '1850.00', 'decision': 'accept',
            'note': 'S4 independent central custody'}))
        ok(api('reviewer', 'POST', f'/api/shifts/{central}/review', {'decision': 'approve'}))
        for sid, cash_value in zip(shift_ids, (10000, 20000, 30000)):
            summary = ok(api('owner', 'GET', f'/api/shifts/{sid}/daily-report'))
            assert summary['status'] == 'closed' and summary['expected_piasters'] == cash_value, summary
        summary = ok(api('owner', 'GET', f'/api/shifts/{central}/daily-report'))
        assert summary['status'] == 'closed' and summary['expected_piasters'] == 185000, summary
        daily = ok(api('owner', 'GET', '/api/shifts/day-summary',
                       params={'business_date': day}))
        assert len(daily['stations']) == 4 and daily['shift_coverage_complete'], daily
        assert daily['pending_accounting_review'] == 0, daily
        assert not daily['financially_certified']

        # All shifts have now closed, but an unapproved bank statement must
        # still block financial month-close before even checking the calendar.
        pre_bank = ok(api('owner', 'GET', '/api/periods/preflight',
                          params={'period': month}))
        assert not pre_bank['ready'] and 'البنك' in pre_bank['reason'], pre_bank
        assert api('owner', 'POST', '/api/periods/close', {'period': month}).status_code == 409
        ok(api('bank_reviewer', 'POST', f'/api/bank-reconciliation/{batch}/approve',
               {'note': 'S4 separate bank confirmation'}))
        settlements = ok(api('owner', 'GET', '/api/inventory/supplier-settlements'))
        assert settlements['supplier_booked_piasters'] == 6000
        assert settlements['bank_confirmed_piasters'] == 6000
        assert settlements['supplier_outstanding_confirmed_piasters'] == 4000
        print('S4_CHECKPOINT signed bank statement removes bank-blocking close gate; AP remains 40', flush=True)
        # Bank opening is independently signed via the existing source API.
        from opening_test_helpers import approve_all_openings
        approve_all_openings(clients['owner'], headers['owner'],
                             clients['reviewer'], headers['reviewer'], month)
        patient_control = ok(api('owner', 'GET', '/api/accounting/patient-reconciliation',
                                 params={'period': month}))
        assert patient_control['matched'], patient_control
        cash_control = ok(api('owner', 'GET', '/api/accounting/treasury-reconciliation',
                              params={'period': month}))
        assert cash_control['matched'], cash_control
        with connect() as c:
            def physical_balance(code):
                return c.execute('''SELECT f.opening_piasters+COALESCE(
                      (SELECT SUM(m.amount_piasters) FROM fund_movements m WHERE m.fund_id=f.id),0)
                      FROM funds f WHERE f.code=?''', (code,)).fetchone()[0]
            assert physical_balance('cash_sub') == 0
            assert physical_balance('cash_main') == 185000
            assert physical_balance('bank') == 14000
            assert c.execute("SELECT COUNT(*) FROM shift_sessions WHERE status='closed'").fetchone()[0] == 4
            assert c.execute("SELECT COUNT(*) FROM cashier_treasury_transfers").fetchone()[0] == 3
            assert c.execute("SELECT COUNT(*) FROM bank_statement_batches WHERE status='approved'").fetchone()[0] == 1
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            debits, credits = c.execute('''SELECT COALESCE(SUM(l.debit_piasters),0),
                      COALESCE(SUM(l.credit_piasters),0) FROM gl_lines l
                      JOIN gl_journals j ON j.id=l.journal_id WHERE j.status='posted' ''').fetchone()
            assert debits == credits, (debits, credits)
            assert ledger.trial_balance(c, month)['balanced']
        denied = ok(api('owner', 'GET', '/api/periods/preflight',
                        params={'period': month}))
        assert not denied['ready'], denied
        assert 'الجاري' in denied['reason'] or 'مستقبلي' in denied['reason'], denied
        assert api('owner', 'POST', '/api/periods/close', {'period': month}).status_code == 409
        if not use_http:
            # Simulated post-month clock IN THIS IN-PROCESS TEST ONLY. Never
            # apply any such override to the hospital app or HTTP subprocess.
            with patch('app.current_month', return_value='9999-12'):
                pre = ok(api('owner', 'GET', '/api/periods/preflight',
                             params={'period': month}))
                assert pre['ready'], pre
                assert ok(api('owner', 'POST', '/api/periods/close',
                              {'period': month}))['closed'] == month
            assert api('owner', 'POST', '/api/periods/close', {'period': month}).status_code == 409
        with connect() as c:
            count_closed = c.execute('SELECT COUNT(*) FROM periods WHERE period IN (?,?)',
                             (month, prior_last[:7])).fetchone()[0]
            assert count_closed == (1 if use_http else 2), count_closed
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            if not use_http:
                assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='close_period'").fetchone()[0] == 1
        if use_http:
            from s3_http_transport import transport_info
            info = transport_info()
            assert info['http_requests'] > 100, info
            print('S4_HTTP_TRANSPORT', info, flush=True)
        print('PASS S4 ONE DATABASE: patient invoice/collection 100; shifts 600; old envelope 1300; '
              'cash expense 50; treasury 1850; vendor AP 40; bank balance 140; GL balanced; ' +
              ('real-clock month close blocked over real HTTP' if use_http else
               'real-clock month close blocked, simulated post-month in-process close passed'), flush=True)





if __name__ == '__main__':
    try:
        run()
    except Exception:
        if os.getenv('S4_REAL_HTTP') == '1':
            # Preserve the real Uvicorn traceback for intermittent HTTP 500s.
            import s3_http_transport
            if s3_http_transport._log:
                s3_http_transport._log.seek(0)
                print('S4_UVICORN_FAILURE_TRACE',
                      s3_http_transport._log.read()[-12000:], flush=True)
        raise
    finally:
        if os.getenv('S4_REAL_HTTP') == '1':
            from s3_http_transport import shutdown_server
            shutdown_server()
