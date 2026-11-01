"""G3I TDD: invoice due schedules are gross AP timing only, not AP balances or payments."""
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3i-dues-') as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic-g3i-owner-password')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from inventory import month_close_inventory_issue
        from fastapi.testclient import TestClient
        clients={key:TestClient(app) for key in ('owner','buyer','reviewer','different','outsider')}
        def expect(resp,status=200):
            assert resp.status_code==status,(status,resp.status_code,resp.text[:700])
            return resp.json() if status==200 else {}
        def login(key,password):
            return {'X-CSRF-Token':expect(clients[key].post('/api/login',json={
                'username':'owner' if key=='owner' else 'g3i_'+key,'password':password}))['csrf']}
        auth={'owner':login('owner','synthetic-g3i-owner-password')}
        actors={}
        for key,role in [('buyer','clerk'),('reviewer','reviewer'),('different','reviewer'),('outsider','clerk')]:
            actors[key]=expect(clients['owner'].post('/api/users',headers=auth['owner'],json={
                'username':'g3i_'+key,'password':'synthetic-g3i-actor-password','role':role}))['id']
            auth[key]=login(key,'synthetic-g3i-actor-password')
        for key,prepare,approve in [('buyer',True,False),('reviewer',False,True),('different',True,True)]:
            expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
                'user_id':actors[key],'can_prepare':prepare,'can_approve':approve,
                'reason':'G3I synthetic distinct supplier review roles'}))
        today=datetime.now(ZoneInfo('Africa/Cairo')).date()
        day=today.isoformat()
        later=(today+timedelta(days=45)).isoformat()
        much_later=(today+timedelta(days=105)).isoformat()
        vendor=expect(clients['owner'].post('/api/inventory/vendors',headers=auth['owner'],json={
            'code':'G3I-VENDOR','name':'Synthetic non-drug supply vendor'}))['id']
        item=expect(clients['owner'].post('/api/inventory/items',headers=auth['owner'],json={
            'code':'G3I-CONSUMABLE','name':'Synthetic consumable test','unit':'piece'}))['id']
        po=expect(clients['buyer'].post('/api/inventory/purchase-orders',headers=auth['buyer'],json={
            'vendor_id':vendor,'ordered_on':day,'order_ref':'G3I-PURCHASE-001',
            'evidence_ref':'SYNTH-G3I-PURCHASE-APPROVAL','request_id':'g3i_purchase_0001',
            'lines':[{'item_id':item,'quantity':5,'unit_cost':'20.00'}]}))['id']
        expect(clients['reviewer'].post(f'/api/inventory/purchase-orders/{po}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Synthetic independent purchase review'}))
        receipt=expect(clients['buyer'].post('/api/inventory/receipts',headers=auth['buyer'],json={
            'vendor_id':vendor,'purchase_order_id':po,'received_on':day,'invoice_ref':'G3I-INV-001',
            'evidence_ref':'SYNTH-G3I-GRN-ORIGINAL','request_id':'g3i_receipt_0001',
            'lines':[{'item_id':item,'quantity':5,'unit_cost':'20.00'}]}))['id']
        expect(clients['reviewer'].post(f'/api/inventory/receipts/{receipt}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Independent GRN physical check'}))
        match=expect(clients['buyer'].post('/api/inventory/supplier-invoices',headers=auth['buyer'],json={
            'receipt_id':receipt,'invoice_date':day,'invoice_ref':'G3I-INV-001','amount':'100.00',
            'evidence_ref':'SYNTH-G3I-ORIGINAL-INVOICE','request_id':'g3i_invoice_match_0001',
            'lines':[{'item_id':item,'quantity':5,'unit_cost':'20.00'}]}))['id']
        expect(clients['reviewer'].post(f'/api/inventory/supplier-invoices/{match}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Synthetic approved exact line match'}))
        # Stronger independent reviewer rule: buyer is NOT temp schedule preparer,
        # but is both invoice and GRN originator; API and SQL must still bar approval.
        with connect() as db:
            with db:
                temp=db.execute('''INSERT INTO inventory_supplier_due_schedules
                    (invoice_match_id,scheduled_on,terms_ref,created_by,created_at) VALUES(?,?,?,?,?)''',
                    (match,day,'SYNTH-TERMS-UNTRUSTED',actors['different'],day)).lastrowid
                db.execute('INSERT INTO inventory_supplier_due_lines(schedule_id,line_no,due_on,amount_piasters) VALUES(?,?,?,?)',
                    (temp,1,later,10000))
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
            'user_id':actors['buyer'],'can_prepare':True,'can_approve':True,
            'reason':'Synthetic original GRN writer temporary review grant'}))
        expect(clients['buyer'].post(f'/api/inventory/supplier-due-schedules/{temp}/decision',headers=auth['buyer'],json={
            'decision':'approve','note':'Must deny original invoice/GRN preparer'}),403)
        with connect() as db:
            try:db.execute('''UPDATE inventory_supplier_due_schedules
                    SET status='approved',reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?''',
                    (actors['buyer'],day,'Forgery by invoice originator',temp))
            except sqlite3.IntegrityError:db.rollback()
            else:raise AssertionError('SQL allowed invoice creator to approve third party maturity schedule')
        expect(clients['reviewer'].post(f'/api/inventory/supplier-due-schedules/{temp}/decision',headers=auth['reviewer'],json={
            'decision':'reject','note':'Synthetic incorrect terms ref rejected'}))
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
            'user_id':actors['buyer'],'can_prepare':True,'can_approve':False,
            'reason':'End synthetic reviewer escalation test'}))
        body={'invoice_match_id':match,'scheduled_on':day,'terms_ref':'SYNTH-INDEPENDENT-TERMS-001',
              'request_id':'g3i_schedule_0001','lines':[{'due_on':later,'amount':'40.00'},
                                                        {'due_on':much_later,'amount':'60.00'}]}
        expect(clients['outsider'].get('/api/inventory/supplier-aging'),403)
        expect(clients['buyer'].post('/api/inventory/supplier-due-schedules',headers=auth['buyer'],json={
            **body,'request_id':'g3i_invalid_sum_001','lines':[{'due_on':later,'amount':'40.00'}]}),409)
        expect(clients['buyer'].post('/api/inventory/supplier-due-schedules',headers=auth['buyer'],json={
            **body,'request_id':'g3i_invalid_date_001','lines':[{'due_on':'2026-02-30','amount':'100.00'}]}),400)
        scheduled=expect(clients['buyer'].post('/api/inventory/supplier-due-schedules',headers=auth['buyer'],json=body))['id']
        assert expect(clients['buyer'].post('/api/inventory/supplier-due-schedules',headers=auth['buyer'],json=body))['id']==scheduled
        expect(clients['buyer'].post('/api/inventory/supplier-due-schedules',headers=auth['buyer'],json={
            **body,'lines':[{'due_on':later,'amount':'100.00'}]}),409)
        with connect() as db:
            assert month_close_inventory_issue(db,day[:7])
            for sql,args in [
               ('INSERT INTO inventory_supplier_due_lines(schedule_id,line_no,due_on,amount_piasters) VALUES(?,?,?,?)',
                   (scheduled,3,'2026-02-30',100)),
               ('UPDATE inventory_supplier_due_schedules SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?',
                   ('approved',actors['buyer'],day,'BYPASS-SAME-RECEIPT-CREATOR',scheduled)),
               ('INSERT INTO periods(period,closed_by,closed_at) VALUES(?,?,?)',
                   (day[:7],actors['reviewer'],day))]:
                try:db.execute(sql,args)
                except sqlite3.IntegrityError:db.rollback()
                else:raise AssertionError('SQL bypass accepted: '+sql)
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
          'user_id':actors['different'],'can_prepare':True,'can_approve':False,
          'reason':'Synthetic dynamic revocation before schedule decision'}))
        expect(clients['different'].post(f'/api/inventory/supplier-due-schedules/{scheduled}/decision',
          headers=auth['different'],json={'decision':'approve','note':'Live revocation must block'}),403)
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
          'user_id':actors['different'],'can_prepare':True,'can_approve':True,
          'reason':'Synthetic independent reviewer grant restored'}))
        expect(clients['buyer'].post(f'/api/inventory/supplier-due-schedules/{scheduled}/decision',headers=auth['buyer'],json={
            'decision':'approve','note':'Must reject self approval'}),403)
        # Invoice or GRN author cannot review schedule even if different user created it.
        expect(clients['different'].post(f'/api/inventory/supplier-due-schedules/{scheduled}/decision',headers=auth['different'],json={
            'decision':'approve','note':'Independent from this schedule only'}),200)
        # Multiple attempts must not alter immutable status.
        expect(clients['reviewer'].post(f'/api/inventory/supplier-due-schedules/{scheduled}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Double approval forbidden'}),409)
        schedules=expect(clients['reviewer'].get('/api/inventory/supplier-due-schedules'))
        assert any(x['id']==scheduled and x['status']=='approved' for x in schedules['schedules'])
        assert len([x for x in schedules['lines'] if x['schedule_id']==scheduled])==2
        aging=expect(clients['reviewer'].get('/api/inventory/supplier-aging?as_of='+day))
        assert aging['scheduled_total_piasters']==10000 and aging['unscheduled_total_piasters']==0,aging
        assert aging['future_piasters']==10000 and aging['payment_posted_piasters']==0,aging
        aged=expect(clients['reviewer'].get('/api/inventory/supplier-aging?as_of='+much_later))
        assert aged['due_today_piasters']==6000 and aged['over_30_piasters']==4000,aged
        with connect() as db:
            assert month_close_inventory_issue(db,day[:7]) is None
            ap=db.execute("""SELECT COALESCE(SUM(l.credit_piasters-l.debit_piasters),0) FROM gl_lines l
              JOIN gl_journals j ON j.id=l.journal_id JOIN gl_accounts a ON a.id=l.account_id
              WHERE a.code='2200' AND j.status='posted'""").fetchone()[0]
            assert ap==10000,ap
            for statement,args in [
                ('UPDATE inventory_supplier_due_schedules SET terms_ref=? WHERE id=?',('FAKE-TERMS',scheduled)),
                ('DELETE FROM inventory_supplier_due_schedules WHERE id=?',(scheduled,)),
                ('UPDATE inventory_supplier_due_lines SET amount_piasters=1 WHERE schedule_id=?',(scheduled,)),
                ('DELETE FROM inventory_supplier_due_lines WHERE schedule_id=?',(scheduled,))]:
                try:db.execute(statement,args)
                except sqlite3.IntegrityError:db.rollback()
                else:raise AssertionError('SQL due evidence not immutable: '+statement)
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS G3I supplier due timing, TDD SQL/API controls, no payments or duplicate AP')

if __name__=='__main__':run()
