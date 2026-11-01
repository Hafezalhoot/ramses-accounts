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
        now=datetime.now(ZoneInfo('Africa/Cairo')).date();day=now.isoformat();receipt_day=(now-timedelta(days=1)).isoformat()
        soon=(now+timedelta(days=24)).isoformat();later=(now+timedelta(days=75)).isoformat()
        vendor=expect(clients['owner'].post('/api/inventory/vendors',headers=auth['owner'],json={
            'code':'G3J-VENDOR','name':'Synthetic supplier only'}))['id']
        item=expect(clients['owner'].post('/api/inventory/items',headers=auth['owner'],json={
            'code':'G3J-GAUZE','name':'Synthetic test non-drug supply','unit':'piece'}))['id']
        po=expect(clients['buyer'].post('/api/inventory/purchase-orders',headers=auth['buyer'],json={
            'vendor_id':vendor,'ordered_on':receipt_day,'order_ref':'G3J-PO-001',
            'evidence_ref':'G3J-ORIGINAL-SYNTHETIC-PO','request_id':'g3j_purchase_0001',
            'lines':[{'item_id':item,'quantity':10,'unit_cost':'10.00'}]}))['id']
        expect(clients['reviewer'].post(f'/api/inventory/purchase-orders/{po}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Approved synthetic purchase'}))
        receipt=expect(clients['buyer'].post('/api/inventory/receipts',headers=auth['buyer'],json={
            'vendor_id':vendor,'received_on':receipt_day,'purchase_order_id':po,'invoice_ref':'G3J-INV-001',
            'evidence_ref':'G3J-SYNTHETIC-GRN-001','request_id':'g3j_receipt_0001',
            'lines':[{'item_id':item,'quantity':10,'unit_cost':'10.00'}]}))['id']
        expect(clients['reviewer'].post(f'/api/inventory/receipts/{receipt}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Approved synthetic goods arrival'}))
        # A GRN posts to AP even BEFORE the supplier invoice is matched.
        open_grn=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':day}))
        assert open_grn['control_2200_piasters']==10000 and open_grn['reconciled'],open_grn
        assert open_grn['vendors'][0]['approved_unmatched_grn_count']==1,open_grn
        yesterday=(now-timedelta(days=1)).isoformat()
        prior=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':yesterday}))
        assert prior['control_2200_piasters']==10000 and prior['vendors'][0]['approved_unmatched_grn_count']==1,prior
        invoice=expect(clients['buyer'].post('/api/inventory/supplier-invoices',headers=auth['buyer'],json={
            'receipt_id':receipt,'invoice_date':day,'invoice_ref':'G3J-INV-001','amount':'100.00',
            'evidence_ref':'G3J-SYNTHETIC-INVOICE','request_id':'g3j_invoice_0001',
            'lines':[{'item_id':item,'quantity':10,'unit_cost':'10.00'}]}))['id']
        expect(clients['reviewer'].post(f'/api/inventory/supplier-invoices/{invoice}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Approved independent invoice match'}))
        # Invoice review was signed TODAY, so yesterday the GRN must still be
        # reported as unmatched, even though its currently stored status is approved.
        past=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':receipt_day}))
        assert past['control_2200_piasters']==10000 and past['vendors'][0]['approved_unmatched_grn_count']==1,past
        early=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={
            'as_of':(now-timedelta(days=2)).isoformat()}))
        assert early['control_2200_piasters']==0 and early['attributed_2200_piasters']==0,early
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
        expect(clients['approver'].post(f'/api/inventory/supplier-payment-requests/{pay_id}/decision',headers=auth['approver'],json={
            'decision':'approve','note':'Independent supplier authorization'}))
        actors['payer']=expect(clients['owner'].post('/api/users',headers=auth['owner'],json={
            'username':'g3j_payer','password':'synthetic-g3j-actor-secret','role':'clerk'}))['id']
        actors['bankreviewer']=expect(clients['owner'].post('/api/users',headers=auth['owner'],json={
            'username':'g3j_bankreviewer','password':'synthetic-g3j-actor-secret','role':'reviewer'}))['id']
        clients['payer']=TestClient(app);clients['bankreviewer']=TestClient(app)
        auth['payer']=login('payer','synthetic-g3j-actor-secret')
        auth['bankreviewer']=login('bankreviewer','synthetic-g3j-actor-secret')
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
            'user_id':actors['payer'],'can_prepare':True,'can_approve':False,'reason':'Synthetic G3K authorized bank maker'}))
        with connect() as c:
            bank=c.execute("SELECT id FROM funds WHERE code='bank'").fetchone()[0]
            admin=c.execute("SELECT id FROM departments WHERE code='ADMIN'").fetchone()[0]
            category=c.execute("SELECT id FROM categories WHERE code='supplier_ap_settlement'").fetchone()
            c.execute('UPDATE funds SET opening_piasters=20000 WHERE id=?',(bank,))
        assert category is not None,'G3K protected category missing'
        assert all(x['code']!='supplier_ap_settlement' for x in expect(
            clients['payer'].get('/api/lookups'))['categories']), 'Protected supplier AP category leaked into generic voucher picker'
        expect(clients['owner'].post('/api/fund-access',headers=auth['owner'],json={
            'user_id':actors['payer'],'fund_id':bank,'can_submit':True,'reason':'G3K test maker bank grant'}))
        expect(clients['owner'].post('/api/fund-access',headers=auth['owner'],json={
            'user_id':actors['bankreviewer'],'fund_id':bank,'can_approve':True,
            'reason':'G3K independent bank reviewer grant'}))
        body={'booked_on':day,'bank_fund_id':bank,'bank_reference':'G3K-TEST-BANK-REF-01',
              'request_id':'g3kbankvoucher0001'}
        expect(clients['payer'].post('/api/vouchers',headers=auth['payer'],json={
            'date':day,'kind':'payment','shift':'central','department_id':admin,
            'category_id':category[0],'from_fund_id':bank,'amount':'60.00',
            'description':'Unlinked supplier settlement must be blocked','reference_no':'FORGED-UNLINKED'}),403)
        expect(clients['outsider'].post(f'/api/inventory/supplier-payment-requests/{pay_id}/bank-voucher',
            headers=auth['outsider'],json=body),403)
        voucher=expect(clients['payer'].post(f'/api/inventory/supplier-payment-requests/{pay_id}/bank-voucher',
            headers=auth['payer'],json=body))
        vid=voucher['voucher_id'];assert voucher['status']=='pending'
        assert expect(clients['payer'].post(f'/api/inventory/supplier-payment-requests/{pay_id}/bank-voucher',
            headers=auth['payer'],json=body))['voucher_id']==vid
        expect(clients['payer'].post(f'/api/inventory/supplier-payment-requests/{pay_id}/bank-voucher',
            headers=auth['payer'],json={**body,'bank_reference':'DIFFERENT-BANK-REF'}),409)
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==base_journal
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==base_movements
            assert c.execute('SELECT status FROM vouchers WHERE id=?',(vid,)).fetchone()[0]=='pending'
            try:c.execute('UPDATE vouchers SET category_id=? WHERE id=?',(
                  c.execute("SELECT id FROM categories WHERE code='inventory_buy'").fetchone()[0],vid))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('Linked AP voucher category could be changed directly via SQLite')
            try:c.execute("UPDATE vouchers SET status='approved',reviewed_by=?,reviewed_at=? WHERE id=?",
                          (actors['approver'],day,vid))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('G3K voucher approved by earlier request reviewer via direct SQLite')
        expect(clients['approver'].post(f'/api/vouchers/{vid}/decision',headers=auth['approver'],json={
            'decision':'approve','reason':'Same request reviewer cannot approve bank payment'}),403)
        expect(clients['bankreviewer'].post(f'/api/vouchers/{vid}/decision',headers=auth['bankreviewer'],json={
            'decision':'approve','reason':'Independent bank payment posting'}))
        with connect() as c:
            paid=c.execute('''SELECT SUM(l.debit_piasters-l.credit_piasters) FROM gl_lines l
                 JOIN gl_journals j ON j.id=l.journal_id JOIN gl_accounts a ON a.id=l.account_id
                 WHERE j.origin='voucher' AND j.source_id=? AND a.code='2200' ''',(vid,)).fetchone()[0]
            assert paid==6000, paid
            credit=c.execute('''SELECT SUM(amount_piasters) FROM fund_movements WHERE voucher_id=? AND fund_id=?''',(vid,bank)).fetchone()[0]
            assert credit==-6000,credit
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==base_movements+1
        report=expect(clients['owner'].get('/api/inventory/supplier-settlements'))
        row=next(x for x in report['items'] if x['payment_request_id']==pay_id)
        assert row['booked_piasters']==6000 and row['bank_confirmed_piasters']==0,row
        assert report['supplier_booked_piasters']==6000 and report['bank_confirmed_piasters']==0,report
        # G3L RED/GREEN: the 2200 control account must expose source-mapped
        # GRNs and posted supplier-bank vouchers, not merely matched invoices.
        expect(clients['outsider'].get('/api/inventory/supplier-control-ledger'),403)
        control=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':day}))
        assert control['control_2200_piasters']==4000,control
        assert control['attributed_2200_piasters']==4000 and control['unattributed_2200_piasters']==0,control
        assert control['reconciled'] is True and len(control['vendors'])==1,control
        assert control['vendors'][0]['accrued_piasters']==10000 and control['vendors'][0]['net_payments_piasters']==6000,control
        assert control['vendors'][0]['balance_piasters']==4000,control
        assert control['vendors'][0]['approved_unmatched_grn_count']==0,control
        expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':'2026-02-30'}),400)
        secondary=expect(clients['initiator'].post('/api/inventory/supplier-payment-requests',headers=auth['initiator'],json={
            'due_line_id':due_line,'requested_on':day,'amount':'10.00',
            'evidence_ref':'G3K-SECONDARY-RETRY-REQUEST','request_id':'g3ksecondintent0001'}))['id']
        expect(clients['approver'].post(f'/api/inventory/supplier-payment-requests/{secondary}/decision',headers=auth['approver'],json={
            'decision':'approve','note':'Independent second supplier request'}))
        expect(clients['payer'].post(f'/api/inventory/supplier-payment-requests/{secondary}/bank-voucher',
            headers=auth['payer'],json={'booked_on':day,'bank_fund_id':bank,
            'bank_reference':'G3K-TEST-BANK-REF-01','request_id':'g3kduplicatebankref0001'}),409)
        replacement_body={'booked_on':day,'bank_fund_id':bank,'bank_reference':'G3K-REJECTED-BANK-REF',
                          'request_id':'g3krejectedvoucher0001'}
        rejected=expect(clients['payer'].post(f'/api/inventory/supplier-payment-requests/{secondary}/bank-voucher',
           headers=auth['payer'],json=replacement_body))['voucher_id']
        expect(clients['bankreviewer'].post(f'/api/vouchers/{rejected}/decision',headers=auth['bankreviewer'],json={
            'decision':'reject','reason':'Incorrect synthetic bank instruction'}))
        retry=expect(clients['payer'].post(f'/api/inventory/supplier-payment-requests/{secondary}/bank-voucher',
           headers=auth['payer'],json={**replacement_body,'bank_reference':'G3K-REPLACEMENT-REF',
                     'request_id':'g3kreplacementvoucher0001'}))['voucher_id']
        assert retry!=rejected
        expect(clients['bankreviewer'].post(f'/api/vouchers/{retry}/decision',headers=auth['bankreviewer'],json={
            'decision':'reject','reason':'Second synthetic test refusal; audit retained'}))
        with connect() as c:
            assert c.execute('SELECT count(*) FROM inventory_supplier_bank_vouchers WHERE payment_request_id=?',
                             (secondary,)).fetchone()[0]==2
        # Two rejected bank vouchers must not appear as money movements.
        report=expect(clients['owner'].get('/api/inventory/supplier-settlements'))
        assert report['supplier_booked_piasters']==6000
        csv_bytes=(f'date,amount,description,reference\n{day},-60.00,Supplier bank payment,G3K-TEST-BANK-REF-01\n').encode()
        batch=expect(clients['owner'].post('/api/bank-reconciliation/import',headers=auth['owner'],data={
            'fund_id':bank,'period':day[:7],'opening_balance':'200.00','closing_balance':'140.00'},
            files={'file':('synthetic-g3k.csv',csv_bytes,'text/csv')}))['batch_id']
        match=expect(clients['owner'].get('/api/bank-reconciliation',params={'period':day[:7],'fund_id':bank}))
        line_id=match['lines'][0]['id'];movement=match['unmatched_ledger'][0]['movement_id']
        expect(clients['owner'].post(f'/api/bank-reconciliation/{batch}/match',headers=auth['owner'],json={
            'line_id':line_id,'movement_id':movement,'note':'Synthetic G3K supplier match'}))
        report=expect(clients['owner'].get('/api/inventory/supplier-settlements'))
        row=next(x for x in report['items'] if x['payment_request_id']==pay_id)
        assert row['bank_matched_piasters']==6000 and row['bank_confirmed_piasters']==0,row
        expect(clients['owner'].post(f'/api/vouchers/{vid}/reverse',headers=auth['owner'],json={
            'date':day,'reason':'Cannot reverse an actively matched supplier bank payment'}),409)
        expect(clients['owner'].post('/api/fund-access',headers=auth['owner'],json={
            'user_id':actors['bankreviewer'],'fund_id':bank,'can_submit':True,
            'reason':'G3K synthetic bank reviewer statement permissions'}))
        expect(clients['bankreviewer'].post(f'/api/bank-reconciliation/{batch}/approve',headers=auth['bankreviewer'],json={
            'note':'Independent G3K bank statement signoff'}))
        report=expect(clients['owner'].get('/api/inventory/supplier-settlements'))
        row=next(x for x in report['items'] if x['payment_request_id']==pay_id)
        assert row['bank_confirmed_piasters']==6000,row
        assert report['supplier_booked_piasters']==6000 and report['bank_confirmed_piasters']==6000
        assert report['supplier_outstanding_book_piasters']==4000
        assert report['supplier_outstanding_confirmed_piasters']==4000
        # In a separate synthetic bank fund, a genuinely posted and then reversed
        # payment does not settle the debt; the same approved intent may be retried.
        with connect() as c:
            bank2=c.execute("INSERT INTO funds(code,name,kind,opening_piasters) VALUES('SYN-G3K-BANK2','Independent synthetic bank 2','bank',20000)").lastrowid
        for person,permission_key in [('payer','can_submit'),('bankreviewer','can_approve')]:
            expect(clients['owner'].post('/api/fund-access',headers=auth['owner'],json={
               'user_id':actors[person],'fund_id':bank2,permission_key:True,
               'reason':'Synthetic independent bank 2 payment and reversal test'}))
        third=expect(clients['payer'].post(f'/api/inventory/supplier-payment-requests/{secondary}/bank-voucher',
            headers=auth['payer'],json={'booked_on':day,'bank_fund_id':bank2,
             'bank_reference':'G3K-THIRD-REVERSAL-REF','request_id':'g3kthirdbankvoucher0001'}))['voucher_id']
        expect(clients['bankreviewer'].post(f'/api/vouchers/{third}/decision',headers=auth['bankreviewer'],json={
            'decision':'approve','reason':'Independent bank 2 synthetic approval'}))
        expect(clients['owner'].post(f'/api/vouchers/{third}/reverse',headers=auth['owner'],json={
            'date':day,'reason':'Synthetic misdirected bank 2 payment reversal'}))
        report=expect(clients['owner'].get('/api/inventory/supplier-settlements'))
        assert report['supplier_booked_piasters']==6000,report
        fourth=expect(clients['payer'].post(f'/api/inventory/supplier-payment-requests/{secondary}/bank-voucher',
            headers=auth['payer'],json={'booked_on':day,'bank_fund_id':bank2,
             'bank_reference':'G3K-REISSUED-AFTER-REVERSAL','request_id':'g3kfourthbankvoucher0001'}))['voucher_id']
        expect(clients['bankreviewer'].post(f'/api/vouchers/{fourth}/decision',headers=auth['bankreviewer'],json={
            'decision':'approve','reason':'Independent reissued bank 2 synthetic approval'}))
        report=expect(clients['owner'].get('/api/inventory/supplier-settlements'))
        assert report['supplier_booked_piasters']==7000,report
        assert report['bank_confirmed_piasters']==6000,report
        assert report['supplier_outstanding_book_piasters']==3000
        assert report['supplier_outstanding_confirmed_piasters']==4000
        # Original and reversal journals must both count as of the requested
        # date; current 'reversed' voucher status cannot erase its history.
        control=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':day}))
        assert control['control_2200_piasters']==3000,control
        assert control['attributed_2200_piasters']==3000 and control['reconciled'],control
        assert control['vendors'][0]['net_payments_piasters']==7000,control
        with connect() as c:
            from ledger import _journal,account_by_code
            # A posting that hits 2200 with no vendor source MUST remain
            # unattributed, not silently assigned to the only known vendor.
            extra=_journal(c,entry_date=day,memo='Synthetic unattributed AP opening item',origin='manual',source_id=None,
                  created_by=1,reviewed_by=1,lines=[
                      (account_by_code(c,'1100'),500,0,None),(account_by_code(c,'2200'),0,500,None)])
            assert extra is not None
        control=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':day}))
        assert control['control_2200_piasters']==3500 and control['attributed_2200_piasters']==3000,control
        assert control['unattributed_2200_piasters']==500 and control['reconciled'] is False,control
        assert any(j['journal_id']==extra for j in control['unattributed_journals']),control
        with connect() as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        print('PASS G3K independently approved bank voucher, Dr AP/Cr bank, matched and signed bank evidence')

if __name__=='__main__':run()
