"""G3H RED/GREEN synthetic API + SQLite: approved PO, GRN, 3-way match, no double AP."""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3h-purchasing-') as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='g3h-owner-synthetic-secret')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        clients={name:TestClient(app) for name in ('owner','buyer','checker','outsider')}
        def expect(resp,status=200):
            assert resp.status_code==status,(status,resp.status_code,resp.text[:1000])
            return resp.json() if status==200 else None
        def login(name,pw):
            return {'X-CSRF-Token':expect(clients[name].post('/api/login',json={
                'username':'owner' if name=='owner' else 'g3h_'+name,'password':pw}))['csrf']}
        owner=login('owner','g3h-owner-synthetic-secret')
        actors={}
        for name,role in [('buyer','clerk'),('checker','reviewer'),('outsider','clerk')]:
            actors[name]=expect(clients['owner'].post('/api/users',headers=owner,json={
                'username':'g3h_'+name,'password':'g3h-actor-synthetic-secret','role':role}))['id']
        auth={name:login(name,'g3h-actor-synthetic-secret') for name in actors}
        for name in ('buyer','checker'):
            expect(clients['owner'].post('/api/inventory/access',headers=owner,json={
                'user_id':actors[name],'can_prepare':name=='buyer',
                'can_approve':name=='checker','reason':'Synthetic PO and AP distinct duties'}))
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        vendor=expect(clients['owner'].post('/api/inventory/vendors',headers=owner,json={
            'code':'G3H-VENDOR','name':'Synthetic purchase vendor'}))['id']
        vendor2=expect(clients['owner'].post('/api/inventory/vendors',headers=owner,json={
            'code':'G3H-OTHER','name':'Synthetic other vendor'}))['id']
        item=expect(clients['owner'].post('/api/inventory/items',headers=owner,json={
            'code':'G3H-GAUZE','name':'Synthetic non-drug consumable', 'unit':'piece'}))['id']
        po={'vendor_id':vendor,'ordered_on':day,'order_ref':'G3H-PO-001',
            'evidence_ref':'SYNTH-PO-APPROVAL-REFERENCE','request_id':'g3h_purchase_order_0001',
            'lines':[{'item_id':item,'quantity':5,'unit_cost':'12.50'}]}
        expect(clients['outsider'].get('/api/inventory/purchase-orders'),403)
        r=expect(clients['buyer'].post('/api/inventory/purchase-orders',headers=auth['buyer'],json=po))
        pid=r['id']
        assert expect(clients['buyer'].post('/api/inventory/purchase-orders',headers=auth['buyer'],json=po))['id']==pid
        expect(clients['buyer'].post('/api/inventory/purchase-orders',headers=auth['buyer'],json={
            **po,'lines':[{'item_id':item,'quantity':6,'unit_cost':'12.50'}]}),409)
        receipt={'vendor_id':vendor,'received_on':day,'invoice_ref':'G3H-INVOICE-001',
            'evidence_ref':'G3H-RECEIVED-DOCK-001','purchase_order_id':pid,
            'request_id':'g3h_receipt_grn_0001','lines':[{'item_id':item,'quantity':2,'unit_cost':'12.50'}]}
        expect(clients['buyer'].post('/api/inventory/receipts',headers=auth['buyer'],json=receipt),409)
        expect(clients['buyer'].post(f'/api/inventory/purchase-orders/{pid}/decision',headers=auth['buyer'],json={
            'decision':'approve','note':'Self approval must be forbidden'}),403)
        expect(clients['owner'].post('/api/inventory/access',headers=owner,json={
            'user_id':actors['checker'],'can_prepare':False,'can_approve':False,
            'reason':'Synthetic live reviewer revocation of PO'}))
        expect(clients['checker'].post(f'/api/inventory/purchase-orders/{pid}/decision',headers=auth['checker'],json={
            'decision':'approve','note':'Approved independent purchase limit'}),403)
        expect(clients['owner'].post('/api/inventory/access',headers=owner,json={
            'user_id':actors['checker'],'can_prepare':False,'can_approve':True,
            'reason':'Synthetic restoration of reviewer access'}))
        expect(clients['checker'].post(f'/api/inventory/purchase-orders/{pid}/decision',headers=auth['checker'],json={
            'decision':'approve','note':'Approved independent purchase limit'}))
        expect(clients['checker'].post(f'/api/inventory/purchase-orders/{pid}/decision',headers=auth['checker'],json={
            'decision':'approve','note':'Duplicate reviewer attempt'}),409)
        expect(clients['buyer'].post('/api/inventory/receipts',headers=auth['buyer'],json={
            **receipt,'vendor_id':vendor2,'request_id':'g3h_wrong_vendor_01'}),409)
        expect(clients['buyer'].post('/api/inventory/receipts',headers=auth['buyer'],json={
            **receipt,'request_id':'g3h_wrong_cost_001',
            'lines':[{'item_id':item,'quantity':2,'unit_cost':'15.00'}]}),409)
        rid=expect(clients['buyer'].post('/api/inventory/receipts',headers=auth['buyer'],json=receipt))['id']
        expect(clients['checker'].post(f'/api/inventory/receipts/{rid}/decision',headers=auth['checker'],json={
            'decision':'approve','note':'Approved first partial delivery'}))
        second={**receipt,'invoice_ref':'G3H-INVOICE-002','request_id':'g3h_receipt_grn_0002',
                'lines':[{'item_id':item,'quantity':3,'unit_cost':'12.50'}]}
        rid2=expect(clients['buyer'].post('/api/inventory/receipts',headers=auth['buyer'],json=second))['id']
        expect(clients['buyer'].post('/api/inventory/receipts',headers=auth['buyer'],json={
            **receipt,'invoice_ref':'G3H-INVOICE-OVER','request_id':'g3h_grn_overbook_01',
            'lines':[{'item_id':item,'quantity':1,'unit_cost':'12.50'}]}),409)
        expect(clients['checker'].post(f'/api/inventory/receipts/{rid2}/decision',headers=auth['checker'],json={
            'decision':'approve','note':'Approved second partial delivery'}))
        # PO + GRNs do not create separate AP beyond approved 1100/2200 receipt journal.
        overview=expect(clients['buyer'].get('/api/inventory/overview'))
        assert overview['items'][0]['quantity_on_hand']==5
        assert overview['items'][0]['value_piasters']==6250
        assert len([r for r in overview['purchase_orders'] if r['id']==pid])==1
        report=expect(clients['buyer'].get('/api/inventory/supplier-payables'))
        assert report['total_grn_accrued_piasters']==6250 and report['confirmed_piasters']==0,report
        # Direct SQL must reject repeated item lines that collectively overbook a PO.
        extra_po=expect(clients['buyer'].post('/api/inventory/purchase-orders',headers=auth['buyer'],json={
            **po,'order_ref':'G3H-SQL-DUP-PO','request_id':'g3h_sql_dup_purchase_order_01'}))['id']
        expect(clients['checker'].post(f'/api/inventory/purchase-orders/{extra_po}/decision',headers=auth['checker'],json={
            'decision':'approve','note':'Synthetic direct SQL duplicate line test'}))
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cur=db.execute('''INSERT INTO inventory_receipts(vendor_id,received_on,invoice_ref,evidence_ref,created_by,created_at)
                  VALUES(?,?,?,?,?,?)''',(vendor,day,'G3H-DUPLICATE-SQL-INV','SYN-EXTRA-SQL-GRN',actors['buyer'],day))
            direct_rid=cur.lastrowid
            for _ in (1,2):
                db.execute('''INSERT INTO inventory_receipt_lines(receipt_id,item_id,quantity,unit_cost_piasters)
                    VALUES(?,?,3,1250)''',(direct_rid,item))
            try:db.execute('INSERT INTO inventory_receipt_purchase_links(receipt_id,purchase_order_id) VALUES (?,?)',
                           (direct_rid,extra_po))
            except sqlite3.IntegrityError:db.rollback()
            else:raise AssertionError('Direct SQL overbooked PO using duplicate GRN item rows')
        from inventory import month_close_inventory_issue
        with connect() as db:
            assert 'فاتورة' in month_close_inventory_issue(db,day[:7]),month_close_inventory_issue(db,day[:7])
            try:
                db.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES(?,?,?)',
                           (day[:7],1,day))
            except sqlite3.IntegrityError:db.rollback()
            else:raise AssertionError('Month closed with PO-linked GRNs missing supplier invoice confirmation')
        invoice={'receipt_id':rid,'invoice_date':day,'invoice_ref':'G3H-INVOICE-001',
                 'amount':'25.00','evidence_ref':'G3H-INVOICE-PDF-FINGERPRINT',
                 'lines':[{'item_id':item,'quantity':2,'unit_cost':'12.50'}],
                 'request_id':'g3h_supplier_invoice_01'}
        expect(clients['buyer'].post('/api/inventory/supplier-invoices',headers=auth['buyer'],json={
            **invoice,'amount':'26.00','request_id':'g3h_bad_supplier_invoice'}),409)
        expect(clients['buyer'].post('/api/inventory/supplier-invoices',headers=auth['buyer'],json={
            **invoice,'invoice_ref':'DIFFERENT-REF','request_id':'g3h_bad_reference_01'}),409)
        # Same invoice total but different item quantity and unit price is NOT a 3-way match.
        expect(clients['buyer'].post('/api/inventory/supplier-invoices',headers=auth['buyer'],json={
            **invoice,'lines':[{'item_id':item,'quantity':1,'unit_cost':'25.00'}],
            'request_id':'g3h_wrong_line_same_total_01'}),409)
        match=expect(clients['buyer'].post('/api/inventory/supplier-invoices',headers=auth['buyer'],json=invoice))['id']
        assert expect(clients['buyer'].post('/api/inventory/supplier-invoices',headers=auth['buyer'],json=invoice))['id']==match
        expect(clients['buyer'].post(f'/api/inventory/supplier-invoices/{match}/decision',headers=auth['buyer'],json={
            'decision':'approve','note':'Cannot self approve match'}),403)
        expect(clients['checker'].post(f'/api/inventory/supplier-invoices/{match}/decision',headers=auth['checker'],json={
            'decision':'approve','note':'Independent comparison of PO, GRN and supplier invoice'}))
        expect(clients['checker'].post(f'/api/inventory/supplier-invoices/{match}/decision',headers=auth['checker'],json={
            'decision':'approve','note':'Repeated decision'}),409)
        report=expect(clients['buyer'].get('/api/inventory/supplier-payables'))
        assert (report['total_grn_accrued_piasters'],report['confirmed_piasters'],report['unmatched_piasters'])==(6250,2500,3750),report
        assert report['payment_posted_piasters']==0
        with connect() as db:
            ap=db.execute("""SELECT COALESCE(SUM(l.credit_piasters-l.debit_piasters),0)
                FROM gl_lines l JOIN gl_journals j ON j.id=l.journal_id
                JOIN gl_accounts a ON a.id=l.account_id WHERE a.code='2200' AND j.status='posted'""").fetchone()[0]
            assert ap==6250,ap
            assert db.execute('SELECT count(*) FROM gl_journals WHERE memo LIKE "INV:PURCHASE%"').fetchone()[0]==2
            for statement,args in [
                ('UPDATE inventory_purchase_orders SET vendor_id=? WHERE id=?',(vendor2,pid)),
                ('UPDATE inventory_receipt_purchase_links SET purchase_order_id=? WHERE receipt_id=?',(pid,rid)),
                ('DELETE FROM inventory_receipt_purchase_links WHERE receipt_id=?',(rid,)),
                ('UPDATE inventory_supplier_invoice_matches SET amount_piasters=1 WHERE id=?',(match,)),
                ('DELETE FROM inventory_supplier_invoice_matches WHERE id=?',(match,)),
                ('UPDATE inventory_supplier_invoice_match_lines SET quantity=1 WHERE match_id=?',(match,)),
                ('DELETE FROM inventory_supplier_invoice_match_lines WHERE match_id=?',(match,))]:
                try: db.execute(statement,args)
                except sqlite3.IntegrityError: db.rollback()
                else: raise AssertionError('Financial source document not SQL-immutable: '+statement)
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        # Reject existing pending invoice-match then allow correcting against same receipt.
        # Direct SQLite cannot approve an invoice with matching header but absent item lines.
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cur=db.execute('INSERT INTO inventory_supplier_invoice_matches(receipt_id,invoice_date,invoice_ref,amount_piasters,evidence_ref,created_by,created_at) VALUES (?,?,?,?,?,?,?)',
                           (rid2,day,'G3H-INVOICE-002',3750,'SYNTH-MISSING-INVOICE-LINES',actors['buyer'],day))
            try:
                db.execute('UPDATE inventory_supplier_invoice_matches SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?',
                           ('approved',actors['checker'],day,'Bypass with absent item level evidence',cur.lastrowid))
            except sqlite3.IntegrityError:db.rollback()
            else:raise AssertionError('Direct SQL approved invoice with no item-level evidence')
        new_invoice={**invoice,'receipt_id':rid2,'invoice_ref':'G3H-INVOICE-002',
                     'amount':'37.50','request_id':'g3h_supplier_invoice_02',
                     'lines':[{'item_id':item,'quantity':3,'unit_cost':'12.50'}]}
        mid2=expect(clients['buyer'].post('/api/inventory/supplier-invoices',headers=auth['buyer'],json=new_invoice))['id']
        expect(clients['checker'].post(f'/api/inventory/supplier-invoices/{mid2}/decision',headers=auth['checker'],json={
            'decision':'reject','note':'Insufficient original supplier document'}))
        assert expect(clients['buyer'].get('/api/inventory/supplier-payables'))['unmatched_piasters']==3750
        mid3=expect(clients['buyer'].post('/api/inventory/supplier-invoices',headers=auth['buyer'],json={
            **new_invoice,'request_id':'g3h_supplier_invoice_corrected_02',
            'evidence_ref':'G3H-REPLACEMENT-INVOICE-REF'}))['id']
        expect(clients['checker'].post(f'/api/inventory/supplier-invoices/{mid3}/decision',headers=auth['checker'],json={
            'decision':'approve','note':'Corrected supplier evidence independently confirmed'}))
        assert expect(clients['owner'].get('/api/inventory/supplier-payables'))['unmatched_piasters']==0
        with connect() as db:
            assert month_close_inventory_issue(db,day[:7]) is None
            db.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES(?,?,?)',(day[:7],1,day))
            db.commit()
            assert db.execute('SELECT COUNT(*) FROM inventory_supplier_invoice_matches WHERE status="approved"').fetchone()[0]==2
        expect(clients['buyer'].post('/api/inventory/purchase-orders',headers=auth['buyer'],json={
            **po,'order_ref':'G3H-SEALED-PO-001','request_id':'g3h_purchase_order_after_close_01'}),409)
        print('PASS G3H PO partial GRNs, exact 3-way invoice match, no extra AP journal, RBAC/SQLite audit')

if __name__=='__main__': run()
