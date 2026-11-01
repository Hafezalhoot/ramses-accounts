"""G3J: independently reviewed supplier-payment intentions, never actual cashbook payments."""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3j-payment-intent-') as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic-g3j-owner-secret')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        clients={key:TestClient(app) for key in ('owner','buyer','reviewer','initiator','approver','outsider')}
        def expect(resp,status=200):
            assert resp.status_code==status,(status,resp.status_code,resp.text[:900])
            return resp.json() if status==200 else {}
        def login(key,pw):
            return {'X-CSRF-Token':expect(clients[key].post('/api/login',json={
                'username':'owner' if key=='owner' else 'g3j_'+key,'password':pw}))['csrf']}
        auth={'owner':login('owner','synthetic-g3j-owner-secret')}
        actors={}
        for key,role in [('buyer','clerk'),('reviewer','reviewer'),('initiator','clerk'),
                         ('approver','reviewer'),('outsider','clerk')]:
            actors[key]=expect(clients['owner'].post('/api/users',headers=auth['owner'],json={
                'username':'g3j_'+key,'password':'synthetic-g3j-actor-secret','role':role}))['id']
            auth[key]=login(key,'synthetic-g3j-actor-secret')
        for key,p,a in [('buyer',True,False),('reviewer',False,True),('initiator',True,False),('approver',False,True)]:
            expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
                'user_id':actors[key],'can_prepare':p,'can_approve':a,
                'reason':'Synthetic G3J financial authorization distinct duties'}))
        now=datetime.now(ZoneInfo('Africa/Cairo')).date();day=now.isoformat()
        soon=(now+timedelta(days=24)).isoformat();later=(now+timedelta(days=75)).isoformat()
        vendor=expect(clients['owner'].post('/api/inventory/vendors',headers=auth['owner'],json={
            'code':'G3J-VENDOR','name':'Synthetic supplier only'}))['id']
        item=expect(clients['owner'].post('/api/inventory/items',headers=auth['owner'],json={
            'code':'G3J-GAUZE','name':'Synthetic test non-drug supply','unit':'piece'}))['id']
        po=expect(clients['buyer'].post('/api/inventory/purchase-orders',headers=auth['buyer'],json={
            'vendor_id':vendor,'ordered_on':day,'order_ref':'G3J-PO-001',
            'evidence_ref':'G3J-ORIGINAL-SYNTHETIC-PO','request_id':'g3j_purchase_0001',
            'lines':[{'item_id':item,'quantity':10,'unit_cost':'10.00'}]}))['id']
        expect(clients['reviewer'].post(f'/api/inventory/purchase-orders/{po}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Approved synthetic purchase'}))
        receipt=expect(clients['buyer'].post('/api/inventory/receipts',headers=auth['buyer'],json={
            'vendor_id':vendor,'received_on':day,'purchase_order_id':po,'invoice_ref':'G3J-INV-001',
            'evidence_ref':'G3J-SYNTHETIC-GRN-001','request_id':'g3j_receipt_0001',
            'lines':[{'item_id':item,'quantity':10,'unit_cost':'10.00'}]}))['id']
        expect(clients['reviewer'].post(f'/api/inventory/receipts/{receipt}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Approved synthetic goods arrival'}))
        invoice=expect(clients['buyer'].post('/api/inventory/supplier-invoices',headers=auth['buyer'],json={
            'receipt_id':receipt,'invoice_date':day,'invoice_ref':'G3J-INV-001','amount':'100.00',
            'evidence_ref':'G3J-SYNTHETIC-INVOICE','request_id':'g3j_invoice_0001',
            'lines':[{'item_id':item,'quantity':10,'unit_cost':'10.00'}]}))['id']
        expect(clients['reviewer'].post(f'/api/inventory/supplier-invoices/{invoice}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Approved independent invoice match'}))
        due=expect(clients['buyer'].post('/api/inventory/supplier-due-schedules',headers=auth['buyer'],json={
            'invoice_match_id':invoice,'scheduled_on':day,'terms_ref':'G3J-SYNTHETIC-DUE-REF',
            'request_id':'g3j_schedule_0001','lines':[
                {'due_on':soon,'amount':'70.00'}, {'due_on':later,'amount':'30.00'}]}))['id']
        expect(clients['reviewer'].post(f'/api/inventory/supplier-due-schedules/{due}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Original maturity independent approval'}))
        with connect() as c:
            due_line=c.execute('SELECT id FROM inventory_supplier_due_lines WHERE schedule_id=? AND line_no=1',(due,)).fetchone()[0]
            base_journal=c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
            base_movements=c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
            before_ap=c.execute('''SELECT COALESCE(SUM(l.credit_piasters-l.debit_piasters),0) FROM gl_lines l
              JOIN gl_accounts a ON a.id=l.account_id AND a.code='2200'
              JOIN gl_journals j ON j.id=l.journal_id AND j.status='posted' ''').fetchone()[0]
            assert before_ap==10000
        payment={'due_line_id':due_line,'requested_on':day,'amount':'60.00',
                 'evidence_ref':'G3J-NONPAYING-REQUEST-REF-001','request_id':'g3j_request_0001'}
        expect(clients['outsider'].get('/api/inventory/supplier-payment-requests'),403)
        expect(clients['outsider'].post('/api/inventory/supplier-payment-requests',headers=auth['outsider'],json=payment),403)
        expect(clients['initiator'].post('/api/inventory/supplier-payment-requests',headers=auth['initiator'],json={
            **payment,'amount':'80.00','request_id':'g3j_overpaid_0001'}),409)
        pay_id=expect(clients['initiator'].post('/api/inventory/supplier-payment-requests',headers=auth['initiator'],json=payment))['id']
        assert expect(clients['initiator'].post('/api/inventory/supplier-payment-requests',headers=auth['initiator'],json=payment))['id']==pay_id
        expect(clients['initiator'].post('/api/inventory/supplier-payment-requests',headers=auth['initiator'],json={
            **payment,'amount':'25.00'}),409)
        expect(clients['initiator'].post('/api/inventory/supplier-payment-requests',headers=auth['initiator'],json={
            **payment,'amount':'15.00','request_id':'g3j_overage_0001'}),409)
        expect(clients['initiator'].post(f'/api/inventory/supplier-payment-requests/{pay_id}/decision',headers=auth['initiator'],json={
            'decision':'approve','note':'Self approval forbidden'}),403)
        with connect() as c:
            try:c.execute('''UPDATE inventory_supplier_payment_requests SET status='approved',reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?''',
                          (actors['buyer'],day,'Forged request review by invoice source',pay_id))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('SQLite authorized invoice creator')
            try:c.execute('''INSERT INTO inventory_supplier_payment_requests
                (due_line_id,requested_on,amount_piasters,evidence_ref,created_by,created_at)
                VALUES(?,?,?,?,?,?)''',(due_line,day,2000,'G3J-CAP-OVER-SQL',actors['initiator'],day))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('SQLite over-reserved approved due line')
            try:c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES(?,?,?)',(day[:7],actors['owner'] if 'owner' in actors else actors['reviewer'],day))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('SQLite month close with pending G3J request')
        # Vendor can be disabled after the request is prepared: no later approval is safe.
        with connect() as c:
            c.execute('UPDATE inventory_vendors SET active=0 WHERE id=?',(vendor,))
        expect(clients['approver'].post(f'/api/inventory/supplier-payment-requests/{pay_id}/decision',headers=auth['approver'],json={
            'decision':'approve','note':'Inactive supplier must not be authorized'}),409)
        with connect() as c:
            try:c.execute('''UPDATE inventory_supplier_payment_requests
                SET status='approved',reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?''',
                (actors['approver'],day,'Forged approval of disabled supplier',pay_id))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('SQLite approved inactive supplier request')
            c.execute('UPDATE inventory_vendors SET active=1 WHERE id=?',(vendor,))
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
            'user_id':actors['approver'],'can_prepare':False,'can_approve':False,
            'reason':'Synthetic reviewer revocation before approval'}))
        expect(clients['approver'].post(f'/api/inventory/supplier-payment-requests/{pay_id}/decision',headers=auth['approver'],json={
            'decision':'approve','note':'Revoked reviewer cannot approve'}),403)
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
            'user_id':actors['approver'],'can_prepare':False,'can_approve':True,
            'reason':'Synthetic independent review enabled again'}))
        expect(clients['approver'].post(f'/api/inventory/supplier-payment-requests/{pay_id}/decision',headers=auth['approver'],json={
            'decision':'reject','note':'Insufficient documentation synthetic rejection'}))
        replacement=expect(clients['initiator'].post('/api/inventory/supplier-payment-requests',headers=auth['initiator'],json={
            **payment,'request_id':'g3j_replacement_0001','evidence_ref':'G3J-REPLACEMENT-REFERENCE'}))['id']
        expect(clients['buyer'].post(f'/api/inventory/supplier-payment-requests/{replacement}/decision',headers=auth['buyer'],json={
            'decision':'approve','note':'Invoice preparer must not review'}),403) # buyer has no approval grant, also forbidden source
        expect(clients['approver'].post(f'/api/inventory/supplier-payment-requests/{replacement}/decision',headers=auth['approver'],json={
            'decision':'approve','note':'Independent authorization; not a cashbook payment'}))
        expect(clients['approver'].post(f'/api/inventory/supplier-payment-requests/{replacement}/decision',headers=auth['approver'],json={
            'decision':'approve','note':'Replay of final approval'}),409)
        requests=expect(clients['reviewer'].get('/api/inventory/supplier-payment-requests'))
        assert requests['scope']=='AUTHORIZATION_ONLY_NO_PAYMENT'
        assert any(x['id']==replacement and x['status']=='approved' for x in requests['requests'])
        first=next(x for x in requests['eligible_lines'] if x['id']==due_line)
        assert first['reserved_piasters']==6000 and first['available_to_request_piasters']==1000,first
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==base_journal
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==base_movements
            assert c.execute('''SELECT COALESCE(SUM(l.credit_piasters-l.debit_piasters),0) FROM gl_lines l
                JOIN gl_accounts a ON a.id=l.account_id AND a.code='2200'
                JOIN gl_journals j ON j.id=l.journal_id AND j.status='posted' ''').fetchone()[0]==before_ap
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        aged=expect(clients['reviewer'].get('/api/inventory/supplier-aging'))
        assert aged['payment_posted_piasters']==0 and aged['scheduled_total_piasters']==10000
        print('PASS: G3J preparatory payment authorization, SQLite guards, no cash/GL and capacity controls')


if __name__=='__main__':run()
