"""Synthetic, isolated real-API service fee approval and payable regression.

The fixture never opens operational files. Receipt amounts are direct synthetic
billing rows; decisions and reversals use the real SQLite ledger posting engine.
"""
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    # This assertion is the initial RED: a payable review engine must exist.
    assert importlib.util.find_spec('service_fees'), 'Service fee review engine is missing'
    with tempfile.TemporaryDirectory(prefix='s14-service-fees-') as folder:
        database = Path(folder) / 'synthetic.sqlite3'
        os.environ['RAMSES_DB_PATH'] = str(database)
        for name in ('GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON'):
            os.environ.pop(name, None)
        c = sqlite3.connect(database, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.executescript('''
        CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,role TEXT,active INTEGER DEFAULT 1);
        CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER,csrf TEXT,expires_at TEXT);
        CREATE TABLE departments(id INTEGER PRIMARY KEY,name TEXT);
        CREATE TABLE funds(id INTEGER PRIMARY KEY,name TEXT,kind TEXT,active INTEGER DEFAULT 1,cash_restricted INTEGER DEFAULT 0);
        INSERT INTO users(id,username,role) VALUES(1,'owner','owner'),(2,'maker','clerk'),(3,'reviewer','reviewer'),(4,'second','reviewer');
        INSERT INTO departments VALUES(1,'Synthetic department');
        INSERT INTO funds(id,name,kind) VALUES(1,'Synthetic cash','cash');
        CREATE TABLE billing_points(id INTEGER PRIMARY KEY,code TEXT,name TEXT,kind TEXT,fund_id INTEGER);
        CREATE TABLE billing_point_access(point_id INTEGER,user_id INTEGER,active INTEGER DEFAULT 1,PRIMARY KEY(point_id,user_id));
        CREATE TABLE user_fund_grants(user_id INTEGER,fund_id INTEGER,can_submit INTEGER DEFAULT 0,can_approve INTEGER DEFAULT 0,PRIMARY KEY(user_id,fund_id));
        INSERT INTO billing_points VALUES(1,'SYN','Synthetic point','external',1);
        INSERT INTO billing_point_access VALUES(1,3,1),(1,4,1);
        CREATE TABLE billing_patients(id INTEGER PRIMARY KEY,code TEXT,display_name TEXT);
        CREATE TABLE billing_cases(id INTEGER PRIMARY KEY,case_no TEXT,patient_id INTEGER,default_point_id INTEGER,status TEXT);
        CREATE TABLE billing_case_lines(id INTEGER PRIMARY KEY,case_id INTEGER,service_name_snapshot TEXT,department_id INTEGER,quantity INTEGER,state TEXT);
        CREATE TABLE billing_invoice_draft_lines(id INTEGER PRIMARY KEY,draft_id INTEGER,case_line_id INTEGER,total_piasters INTEGER);
        CREATE TABLE billing_invoices(id INTEGER PRIMARY KEY,invoice_no TEXT,draft_id INTEGER,case_id INTEGER,total_piasters INTEGER,status TEXT DEFAULT 'issued');
        CREATE TABLE billing_collections(id INTEGER PRIMARY KEY,case_id INTEGER,invoice_id INTEGER,kind TEXT);
        CREATE TABLE billing_payment_parts(id INTEGER PRIMARY KEY,collection_id INTEGER,fund_id INTEGER,amount_piasters INTEGER);
        CREATE TABLE financial_collection_reallocations(collection_id INTEGER,to_invoice_id INTEGER,to_case_id INTEGER);
        CREATE TABLE billing_advance_allocations(id INTEGER PRIMARY KEY,case_id INTEGER,invoice_id INTEGER,amount_piasters INTEGER);
        CREATE TABLE vouchers(id INTEGER PRIMARY KEY,from_fund_id INTEGER);
        CREATE TABLE late_cash_allocations(id INTEGER PRIMARY KEY,invoice_id INTEGER,amount_piasters INTEGER,voucher_id INTEGER);
        CREATE TABLE late_mixed_clearances(id INTEGER PRIMARY KEY,voucher_id INTEGER);
        CREATE TABLE late_mixed_clearance_lines(id INTEGER PRIMARY KEY,invoice_id INTEGER,line_kind TEXT,amount_piasters INTEGER,clearance_id INTEGER);
        CREATE TABLE billing_credit_requests(id INTEGER PRIMARY KEY,invoice_id INTEGER,amount_piasters INTEGER,status TEXT);
        CREATE TABLE billing_request_keys(request_id TEXT PRIMARY KEY,action TEXT,entity_id INTEGER,payload_hash TEXT,created_by INTEGER,created_at TEXT);
        CREATE TABLE audit_log(id INTEGER PRIMARY KEY,actor_id INTEGER,action TEXT,entity TEXT,entity_id TEXT,details TEXT,created_at TEXT);
        CREATE TABLE sync_status(id INTEGER PRIMARY KEY,dirty INTEGER,revision INTEGER);
        INSERT INTO sync_status VALUES(1,0,0);
        CREATE TABLE fund_movements(id INTEGER PRIMARY KEY,fund_id INTEGER,amount_piasters INTEGER);
        CREATE TABLE periods(period TEXT PRIMARY KEY);
        CREATE TABLE pricing_people(id INTEGER PRIMARY KEY,code TEXT,name TEXT,category TEXT,active INTEGER DEFAULT 1);
        INSERT INTO pricing_people(id,code,name,category) VALUES(1,'A','Synthetic doctor A','doctor'),(2,'B','Synthetic doctor B','doctor'),(3,'N','Synthetic nurse','nurse');
        CREATE TABLE pricing_orders(id INTEGER PRIMARY KEY,case_id INTEGER,created_by INTEGER);
        CREATE TABLE pricing_line_terms(case_line_id INTEGER PRIMARY KEY,order_id INTEGER,gross_piasters INTEGER,net_piasters INTEGER,terms_json TEXT);
        ''')
        schema = (ROOT / 'schema.sql').read_text()
        accounting = schema[schema.index('CREATE TABLE IF NOT EXISTS gl_accounts ('):schema.index('-- V8.1A:')]
        c.executescript(accounting)
        # Exercise the shipped production DDL, without a local scratch dependency.
        start = schema.index('-- S14 service fee review')
        c.executescript(schema[start:])
        from app import app
        import service_fees
        from fastapi.testclient import TestClient
        if not any(getattr(route, 'path', '') == '/api/service-fees/queue' for route in app.routes):
            app.include_router(service_fees.router)
        tokens = {}
        for user_id in (1, 2, 3, 4):
            token = 'synthetic-service-fees-session-' + str(user_id)
            csrf = 'synthetic-csrf-' + str(user_id)
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf,
                      (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()))
            client = TestClient(app)
            client.cookies.set('ramses_sid', token)
            tokens[user_id] = (client, {'X-CSRF-Token': csrf})
        owner, maker, reviewer, second = (tokens[i][0] for i in (1, 2, 3, 4))

        def ok(response, expected=200):
            assert response.status_code == expected, (response.status_code, response.text, expected)
            return response.json()

        def queue(client=reviewer):
            return ok(client.get('/api/service-fees/queue'))['items']

        def setup(line_id, *, quantity=1, gross=10000, net=10000, rules=None, performers=(1, 2), occurrence_performers=None, created_by=2):
            case_id = line_id
            c.execute('INSERT INTO billing_patients VALUES(?,?,?)', (case_id, f'SYN-{case_id}', f'Synthetic patient {case_id}'))
            c.execute('INSERT INTO billing_cases VALUES(?,?,?,?,?)', (case_id, f'CASE-{case_id}', case_id, 1, 'open'))
            c.execute('INSERT INTO billing_case_lines VALUES(?,?,?,?,?,?)', (line_id, case_id, 'Synthetic service', 1, quantity, 'fulfilled'))
            c.execute('INSERT INTO billing_invoice_draft_lines VALUES(?,?,?,?)', (line_id, line_id, line_id, net))
            c.execute('INSERT INTO billing_invoices(id,invoice_no,draft_id,case_id,total_piasters) VALUES(?,?,?,?,?)', (line_id, f'INV-{line_id}', line_id, case_id, net))
            c.execute('INSERT INTO pricing_orders VALUES(?,?,?)', (line_id, case_id, created_by))
            terms = {'rules': rules or [], 'performer_ids': list(performers)}
            if occurrence_performers is not None:
                terms['occurrence_performers'] = occurrence_performers
            c.execute('INSERT INTO pricing_line_terms VALUES(?,?,?,?,?)', (line_id, line_id, gross, net, json.dumps(terms)))
            return line_id

        def receipt(invoice_id, amount, *, advance=False):
            if advance:
                c.execute('INSERT INTO billing_advance_allocations(case_id,invoice_id,amount_piasters) VALUES(?,?,?)', (invoice_id, invoice_id, amount))
            else:
                cur = c.execute('INSERT INTO billing_collections(case_id,invoice_id,kind) VALUES(?,?,?)', (invoice_id, invoice_id, 'invoice'))
                c.execute('INSERT INTO billing_payment_parts(collection_id,fund_id,amount_piasters) VALUES(?,?,?)', (cur.lastrowid, 1, amount))

        def decide(item, action='approve', actor=3, request=None, expected=200):
            client, headers = tokens[actor]
            payload = {k: item[k] for k in ('line_id', 'occurrence_no', 'rule_index', 'person_id', 'calculation_hash')}
            payload.update(expected_amount_piasters=item['amount_piasters'], decision=action,
                           reason='Synthetic independent fee review', request_id=request or f's14_fee_{item["line_id"]}_{item["occurrence_no"]}_{item["rule_index"]}_{item["person_id"]}_{action}')
            return ok(client.post('/api/service-fees/decisions', headers=headers, json=payload), expected)

        # A per-service fixed fee stays 100 per occurrence, shared 50/50.
        fixed = {'target': 'category', 'category': 'doctor', 'when': 'performed', 'kind': 'fixed', 'fixed_amount': '100', 'basis': 'collected', 'distribution': 'shared'}
        setup(1, quantity=2, gross=40000, net=20000, rules=[fixed])
        before_gl = c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
        proposals = queue()
        assert [(p['occurrence_no'], p['person_id'], p['amount_piasters']) for p in proposals] == [(1, 1, 5000), (1, 2, 5000), (2, 1, 5000), (2, 2, 5000)]
        assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0] == before_gl
        assert ok(reviewer.get('/api/service-fees/balances'))['items'] == []
        assert maker.get('/api/service-fees/queue').status_code == 403
        assert maker.get('/api/service-fees/balances').status_code == 403
        # Reject one person's first occurrence only, approve that person's second.
        rejected = decide(proposals[0], 'reject')
        approved = decide(proposals[2])
        assert rejected['journal_id'] is None and approved['journal_id']
        assert decide(proposals[2])['replayed'] is True
        assert len(queue()) == 2
        assert ok(reviewer.get('/api/service-fees/balances'))['items'] == [{'person_id': 1, 'person_name': 'Synthetic doctor A', 'amount_piasters': 5000}]
        assert service_fees.has_active_approvals(c, 1)
        assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0] == 0
        journal = approved['journal_id']
        assert tuple(c.execute('SELECT SUM(debit_piasters),SUM(credit_piasters) FROM gl_lines WHERE journal_id=?', (journal,)).fetchone()) == (5000, 5000)
        assert [(r['code'], r['debit_piasters'], r['credit_piasters']) for r in c.execute('SELECT a.code,l.debit_piasters,l.credit_piasters FROM gl_lines l JOIN gl_accounts a ON a.id=l.account_id WHERE journal_id=? ORDER BY a.code', (journal,))] == [('2320', 0, 5000), ('5196', 5000, 0)]
        # Original approver and order maker cannot independently reverse it.
        reverse = {'reason': 'Synthetic independent correction reversal', 'request_id': 's14_reverse_0000000001'}
        assert reviewer.post(f'/api/service-fees/decisions/{approved["id"]}/reverse', headers=tokens[3][1], json=reverse).status_code == 403
        reversed_row = ok(owner.post(f'/api/service-fees/decisions/{approved["id"]}/reverse', headers=tokens[1][1], json=reverse))
        assert ok(owner.post(f'/api/service-fees/decisions/{approved["id"]}/reverse', headers=tokens[1][1], json=reverse))['replayed']
        assert reversed_row['journal_id'] != journal and not service_fees.has_active_approvals(c, 1)
        assert ok(reviewer.get('/api/service-fees/balances'))['items'] == []
        assert len(queue()) == 2, 'Reversal must suppress regenerated proposal'
        assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0] == 0
        for table, row_id in (('service_fee_decisions', approved['id']), ('service_fee_reversals', reversed_row['id'])):
            for operation in (f'UPDATE {table} SET reason=\'tampered\' WHERE id=?', f'DELETE FROM {table} WHERE id=?'):
                try:
                    c.execute(operation, (row_id,))
                except sqlite3.IntegrityError:
                    pass
                else:
                    raise AssertionError('Fee evidence must be immutable')

        # Half the discounted price collected: 20% of 25 = 5, shared => 2.50;
        # discount-independent: 20% of (100*25/50) = 10, shared => 5.
        percent = {'target': 'category', 'category': 'doctor', 'when': 'performed', 'percentage': '20', 'distribution': 'shared', 'basis': 'collected'}
        setup(2, gross=10000, net=5000, rules=[percent, dict(percent, discount_affects=False)])
        receipt(2, 2500)
        items = [x for x in queue() if x['line_id'] == 2]
        assert [(x['rule_index'], x['person_id'], x['amount_piasters']) for x in items] == [(0, 1, 250), (0, 2, 250), (1, 1, 500), (1, 2, 500)]
        partial = decide(items[0], request='s14_partial_approval_0001')
        stale = items[1]
        receipt(2, 2500, advance=True)
        decide(stale, request='s14_stale_approval_00001', expected=409)
        delta = next(x for x in queue() if x['line_id'] == 2 and x['rule_index'] == 0 and x['person_id'] == 1)
        assert delta['amount_piasters'] == 250 and delta['previously_approved_piasters'] == 250
        decide(delta, request='s14_delta_approval_00001')
        assert sum(x['amount_piasters'] for x in ok(owner.get('/api/service-fees/balances'))['items']) == 500
        decide(next(x for x in queue() if x['line_id'] == 2 and x['rule_index'] == 0 and x['person_id'] == 2), 'reject', request='s14_permanent_reject_001')
        assert not any(x['line_id'] == 2 and x['rule_index'] == 0 and x['person_id'] == 2 for x in queue())

        # Maker-checker includes the owner, and person/performed differs from always.
        setup(3, rules=[dict(percent, target='person', person_id=1)], created_by=1)
        receipt(3, 10000)
        own = next(x for x in queue(owner) if x['line_id'] == 3)
        decide(own, actor=1, request='s14_owner_self_denied_01', expected=403)
        assert service_fees.calculate_rule_shares(c, dict(percent, target='person', person_id=3), [1, 2], 10000) == []
        always = service_fees.calculate_rule_shares(c, dict(percent, target='person', person_id=3, when='always'), [1, 2], 10000)
        assert always == [{'person_id': 3, 'person_name': 'Synthetic nurse', 'amount_piasters': 2000}]
        # Quote projection must preserve occurrence-level indivisible-piaster splits.
        tiny_fixed = dict(fixed, fixed_amount='0.01')
        assert service_fees.calculate_rule_shares(c, tiny_fixed, [1, 2], 2, quantity=2) == [
            {'person_id': 1, 'person_name': 'Synthetic doctor A', 'amount_piasters': 2}]
        assert service_fees.calculate_rule_shares(c, dict(percent, percentage='100'), [1, 2], 2, quantity=2) == [
            {'person_id': 1, 'person_name': 'Synthetic doctor A', 'amount_piasters': 2}]
        # Credits cap the received earning basis; corrected allocations use destination.
        setup(4, rules=[dict(percent, target='person', person_id=1)])
        receipt(4, 10000)
        c.execute("INSERT INTO billing_credit_requests(invoice_id,amount_piasters,status) VALUES(4,4000,'approved')")
        assert next(x for x in queue() if x['line_id'] == 4)['amount_piasters'] == 1200
        setup(5, rules=[dict(percent, target='person', person_id=1)])
        col_id = c.execute('SELECT id FROM billing_collections WHERE invoice_id=4').fetchone()[0]
        c.execute('INSERT INTO financial_collection_reallocations VALUES(?,?,?)', (col_id, 5, 5))
        assert not any(x['line_id'] == 4 for x in queue())
        assert next(x for x in queue() if x['line_id'] == 5)['amount_piasters'] == 2000
        # Proration rounds the final fee once: 50% * (5 * 1/2) = 1.25 => 1 piaster.
        setup(6, gross=5, net=2, rules=[dict(percent, target='person', person_id=1, percentage='50', discount_affects=False)])
        receipt(6, 1)
        assert next(x for x in queue() if x['line_id'] == 6)['amount_piasters'] == 1
        # Historical envelope allocations also retain their source-fund scope.
        c.execute("INSERT INTO funds(id,name,kind) VALUES(2,'Synthetic restricted wallet','wallet')")
        setup(7, rules=[dict(percent, target='person', person_id=1)])
        c.execute('INSERT INTO vouchers VALUES(1,2)')
        c.execute('INSERT INTO late_cash_allocations(invoice_id,amount_piasters,voucher_id) VALUES(7,10000,1)')
        setup(8, rules=[dict(percent, target='person', person_id=1)])
        c.execute('INSERT INTO late_mixed_clearances VALUES(1,1)')
        c.execute("INSERT INTO late_mixed_clearance_lines(invoice_id,line_kind,amount_piasters,clearance_id) VALUES(8,'patient_receipt',10000,1)")
        assert {x['line_id'] for x in queue(owner)} >= {7, 8}
        assert not any(x['line_id'] in (7, 8) for x in queue())
        c.execute('INSERT INTO user_fund_grants VALUES(3,2,0,1)')
        assert {x['line_id'] for x in queue()} >= {7, 8}
        c.execute('DELETE FROM user_fund_grants WHERE user_id=3 AND fund_id=2')
        # Different actual people may perform separate occurrences of one order line.
        setup(9, quantity=2, gross=40000, net=20000, rules=[fixed], occurrence_performers=[
            {'occurrence_no': 1, 'person_ids': [1]}, {'occurrence_no': 2, 'person_ids': [2]}])
        occurrences = [x for x in queue() if x['line_id'] == 9]
        assert [(x['occurrence_no'], x['person_id'], x['amount_piasters']) for x in occurrences] == [(1, 1, 10000), (2, 2, 10000)]
        decide(occurrences[0], 'reject', request='s14_specific_person_reject_01')
        assert [(x['occurrence_no'], x['person_id']) for x in queue() if x['line_id'] == 9] == [(2, 2)]
        # Highest-averages receipt allocation is monotone: adding a piaster
        # cannot reduce a previously approved line's received entitlement.
        for index, weight in enumerate((1500, 1500, 900, 500, 500, 200), start=10):
            setup(index, gross=weight, net=weight, rules=[dict(percent, target='person', person_id=1, percentage='100')])
            if index != 10:
                c.execute('UPDATE billing_invoice_draft_lines SET draft_id=10 WHERE id=?', (index,))
                c.execute('UPDATE billing_case_lines SET case_id=10 WHERE id=?', (index,))
                c.execute('UPDATE pricing_orders SET case_id=10 WHERE id=?', (index,))
        c.execute('UPDATE billing_invoices SET total_piasters=5100 WHERE id=10')
        receipt(10, 25)
        monotone = next(x for x in queue() if x['line_id'] == 13)
        assert monotone['amount_piasters'] == 2
        decide(monotone, request='s14_monotone_approval_0001')
        receipt(10, 1)
        assert not any(x['line_id'] == 13 for x in queue())
        # Even when an occurrence receives 0 integer net piasters after discount,
        # full line collection earns its gross-based percentage fee.
        setup(16, quantity=2, gross=200, net=1, rules=[dict(percent, target='person', person_id=1, percentage='50', discount_affects=False)])
        receipt(16, 1)
        assert [(x['occurrence_no'], x['amount_piasters']) for x in queue() if x['line_id'] == 16] == [(1, 50), (2, 50)]
        # Point and restricted-fund grants are current, including on stale decisions/replays.
        visible = next(x for x in queue() if x['line_id'] == 3)
        c.execute('UPDATE billing_point_access SET active=0 WHERE user_id=3')
        assert queue() == []
        assert ok(reviewer.get('/api/service-fees/balances'))['items'] == []
        decide(visible, request='s14_revoked_point_000001', expected=403)
        c.execute('UPDATE billing_point_access SET active=1 WHERE user_id=3')
        c.execute('UPDATE funds SET cash_restricted=1 WHERE id=1')
        assert queue() == []
        c.execute('INSERT INTO user_fund_grants VALUES(3,1,1,0)')
        assert queue()
        decide(visible, request='s14_read_only_fund_00001', expected=403)
        c.execute('UPDATE user_fund_grants SET can_approve=1 WHERE user_id=3')
        decide(visible, request='s14_current_fund_0000001')
        c.execute('UPDATE user_fund_grants SET can_submit=0,can_approve=0 WHERE user_id=3')
        assert queue() == []
        # Cap is disclosed and targeted approvals do not depend on page membership.
        capped = ok(owner.get('/api/service-fees/queue?limit=1'))
        assert len(capped['items']) == 1 and capped['truncated'] and capped['total_proposals'] > 1
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS S14 service fees: individual occurrence/person review; fixed and collected percent; partial deltas; stale/replay/maker/grant guards; immutable approval/reversal; balanced payable GL; no cash movement')
        c.close()


def test_service_fee_review_regression():
    result = subprocess.run([sys.executable, str(Path(__file__).resolve())], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == '__main__':
    run()
