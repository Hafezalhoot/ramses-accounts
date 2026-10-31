"""G3G RED/GREEN: physically rejected return writeoff, separate GL, two-person review.

Synthetic end-to-end API and SQLite proof. A posted RETURN journal and patient
case cost must never be rewritten by a subsequent damaged-stock disposal.
"""
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
    with tempfile.TemporaryDirectory(prefix='ramses-g3g-writeoff-') as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='g3g-test-owner-secret')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        clients={k:TestClient(app) for k in ('owner','clerk','reviewer','doctor','outsider')}
        def check(response,status=200):
            assert response.status_code==status,(status,response.status_code,response.text[:700])
            return response.json() if status==200 else None
        def login(name,pw):
            return {'X-CSRF-Token':check(clients[name].post('/api/login',json={'username':name if name=='owner' else 'g3g_'+name,'password':pw}))['csrf']}
        oh=login('owner','g3g-test-owner-secret')
        actors={}
        for name,role in [('clerk','clerk'),('reviewer','reviewer'),('doctor','clinician'),('outsider','clerk')]:
            actors[name]=check(clients['owner'].post('/api/users',headers=oh,json={
                'username':'g3g_'+name,'password':'g3g-test-actor-secret','role':role}))['id']
        auth={name:login(name,'g3g-test-actor-secret') for name in actors}
        for name in ('clerk','reviewer'):
            check(clients['owner'].post('/api/inventory/access',headers=oh,json={
                'user_id':actors[name], 'can_prepare':name=='clerk',
                'can_approve':name=='reviewer','reason':'Synthetic independent stock writeoff role'}))
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        dept=next(d['id'] for d in check(clients['owner'].get('/api/lookups'))['departments'] if d['code']=='OR')
        point=next(p['id'] for p in check(clients['owner'].get('/api/billing/config'))['points'] if p['kind']=='internal')
        for name in ('clerk','reviewer'):
            check(clients['owner'].post(f'/api/billing/points/{point}/assign',headers=oh,json={
                'user_id':actors[name],'active':True}))
        patient=check(clients['owner'].post('/api/billing/patients',headers=oh,json={
            'display_name':'Synthetic G3G no real patient','request_id':'g3g_patient_0001'}))['id']
        case=check(clients['owner'].post('/api/billing/cases',headers=oh,json={
            'patient_id':patient,'point_id':point,'kind':'operation','business_date':day,
            'request_id':'g3g_case_test_0001'}))['id']
        vendor=check(clients['owner'].post('/api/inventory/vendors',headers=oh,json={
            'code':'G3G-VENDOR','name':'Synthetic G3G wholesaler'}))['id']
        item=check(clients['owner'].post('/api/inventory/items',headers=oh,json={
            'code':'G3G-DISPOSAL','name':'Synthetic non-drug rejected supply', 'unit':'piece'}))['id']
        receipt=check(clients['clerk'].post('/api/inventory/receipts',headers=auth['clerk'],json={
            'vendor_id':vendor,'received_on':day,'invoice_ref':'G3G-TEST-INVOICE-01',
            'evidence_ref':'G3G-SYNTHETIC-RECEIPT','request_id':'g3g_receipt_test_0001',
            'lines':[{'item_id':item,'quantity':5,'unit_cost':'17.25','batch_ref':'G3G-LOT-01'}]}))['id']
        check(clients['reviewer'].post(f'/api/inventory/receipts/{receipt}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Synthetic independent goods receipt signoff'}))
        issue=check(clients['clerk'].post('/api/inventory/issues',headers=auth['clerk'],json={
            'department_id':dept,'case_id':case,'used_on':day,
            'evidence_ref':'G3G-ORIGINAL-ISSUE','request_id':'g3g_issue_test_0001',
            'lines':[{'item_id':item,'quantity':5}]}))['id']
        check(clients['reviewer'].post(f'/api/inventory/issues/{issue}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Synthetic independent original FIFO consumption'}))
        allocation=check(clients['clerk'].get(f'/api/inventory/issues/{issue}/returnable'))['allocations'][0]['issue_allocation_id']
        ret=check(clients['clerk'].post('/api/inventory/returns',headers=auth['clerk'],json={
            'issue_id':issue,'returned_on':day,'evidence_ref':'G3G-RETURN-DOCUMENT',
            'request_id':'g3g_return_test_0001','lines':[{'issue_allocation_id':allocation,'quantity':3}]}))['id']
        financial=check(clients['reviewer'].post(f'/api/inventory/returns/{ret}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Synthetic financially approved physical return'}))
        assert financial['cost_piasters']==5175
        check(clients['owner'].post('/api/billing/clinical/identity-review',headers=oh,json={
            'user_id':actors['doctor'],'professional_name':'Synthetic G3G clinician',
            'registration_reference':'SYN-REG-G3G-01','review_note':'Synthetic professional evidence reviewed',
            'approved':True,'current_password':'g3g-test-owner-secret'}))
        check(clients['owner'].post('/api/billing/clinical/grants',headers=oh,json={
            'user_id':actors['doctor'],'department_id':dept,'active':True}))
        queue=check(clients['doctor'].get('/api/inventory/inspections/queue'))['items']
        assert len(queue)==1,queue
        return_line_id=queue[0]['return_line_id']
        # Stock writeoff is not an alternative to independent clinical rejection.
        draft={'return_line_id':return_line_id,'quantity':2,'disposed_on':day,
               'reason':'damaged','evidence_ref':'G3G-DISPOSAL-001',
               'physical_disposal_confirmed':True,'request_id':'g3g_writeoff_test_0001'}
        check(clients['clerk'].post('/api/inventory/writeoffs',headers=auth['clerk'],json=draft),409)
        check(clients['doctor'].post(f'/api/inventory/inspections/{return_line_id}/decision',headers=auth['doctor'],json={
            'decision':'reject','inspected_on':day,'evidence_ref':'G3G-MEDICAL-REJECTION',
            'note':'Synthetic contaminated packaging is unfit for reuse'}))
        check(clients['doctor'].post('/api/inventory/writeoffs',headers=auth['doctor'],json=draft),403)
        check(clients['outsider'].get('/api/inventory/writeoffs/queue'),403)
        worklist=check(clients['clerk'].get('/api/inventory/writeoffs/queue'))
        assert len(worklist['items'])==1 and worklist['items'][0]['remaining_quantity']==3,worklist
        assert not ({'patient_id','patient_name','case_id','case_no','clinical_note','inspection_note'} & set(worklist['items'][0]))
        stock=check(clients['owner'].get('/api/inventory/overview'))['items'][0]
        assert (stock['quantity_on_hand'],stock['quarantined_quantity'],stock['value_piasters'])==(3,3,5175)
        before=check(clients['owner'].get(f'/api/inventory/cases/{case}/cost'))['total_returned_piasters']
        doc=check(clients['clerk'].post('/api/inventory/writeoffs',headers=auth['clerk'],json=draft))
        wid=doc['id']
        assert check(clients['clerk'].post('/api/inventory/writeoffs',headers=auth['clerk'],json=draft))['id']==wid
        check(clients['clerk'].post('/api/inventory/writeoffs',headers=auth['clerk'],json={
            **draft,'quantity':2,'request_id':'g3g_writeoff_overbook_0001'}),409)
        assert check(clients['owner'].get('/api/inventory/overview'))['items'][0]['value_piasters']==5175
        assert check(clients['owner'].get('/api/inventory/reconciliation',params={'period':day[:7]}))['matched']
        check(clients['clerk'].post(f'/api/inventory/writeoffs/{wid}/decision',headers=auth['clerk'],json={
            'decision':'approve','note':'Self approval must never be permitted'}),403)
        # Revocation is checked when a decision is made, not only at login.
        check(clients['owner'].post('/api/inventory/access',headers=oh,json={
            'user_id':actors['reviewer'],'can_prepare':False,'can_approve':False,
            'reason':'Synthetic immediate reviewer revocation scenario'}))
        check(clients['reviewer'].post(f'/api/inventory/writeoffs/{wid}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Synthetic independent damaged stock posting'}),403)
        check(clients['owner'].post('/api/inventory/access',headers=oh,json={
            'user_id':actors['reviewer'],'can_prepare':False,'can_approve':True,
            'reason':'Synthetic restoration of independent reviewer right'}))
        decided=check(clients['reviewer'].post(f'/api/inventory/writeoffs/{wid}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Synthetic independent damaged stock posting'}))
        assert decided['cost_piasters']==3450 and decided['status']=='approved',decided
        check(clients['reviewer'].post(f'/api/inventory/writeoffs/{wid}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Duplicate decision must not repost'}),409)
        stock=check(clients['owner'].get('/api/inventory/overview'))['items'][0]
        assert (stock['quantity_on_hand'],stock['quarantined_quantity'],stock['available_quantity'],stock['value_piasters'])==(1,1,0,1725),stock
        rec=check(clients['owner'].get('/api/inventory/reconciliation',params={'period':day[:7]}))
        assert rec['matched'] and rec['approved_writeoffs']==1 and rec['value_piasters']==1725,rec
        assert check(clients['owner'].get(f'/api/inventory/cases/{case}/cost'))['total_returned_piasters']==before
        with connect() as db:
            entry=db.execute('''SELECT j.id,j.entry_date,j.memo,a.code,
                SUM(gl.debit_piasters) debit,SUM(gl.credit_piasters) credit
                FROM gl_journals j JOIN gl_lines gl ON gl.journal_id=j.id
                JOIN gl_accounts a ON a.id=gl.account_id WHERE j.id=?
                GROUP BY a.code''',(decided['journal_id'],)).fetchall()
            postings={x['code']:(x['debit'],x['credit']) for x in entry}
            assert postings=={'5195':(3450,0),'1100':(0,3450)},postings
            orig=db.execute('SELECT journal_id,cost_piasters FROM inventory_issue_returns WHERE id=?',(ret,)).fetchone()
            assert tuple(orig)==(financial['journal_id'],5175)
            for sql in ("UPDATE inventory_return_writeoffs SET quantity=1 WHERE id=?",
                        'DELETE FROM inventory_return_writeoffs WHERE id=?',
                        "UPDATE inventory_return_writeoffs SET status='pending' WHERE id=?"):
                try:db.execute(sql,(wid,))
                except sqlite3.IntegrityError:db.rollback()
                else:raise AssertionError('Final writeoff was mutable: '+sql)
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        # Rejecting a subsequent proposal has no inventory/GL effect and frees reservation.
        pending=check(clients['clerk'].post('/api/inventory/writeoffs',headers=auth['clerk'],json={
            **draft,'quantity':1,'request_id':'g3g_writeoff_test_0002','evidence_ref':'G3G-DISPOSAL-002'}))['id']
        check(clients['reviewer'].post(f'/api/inventory/writeoffs/{pending}/decision',headers=auth['reviewer'],json={
            'decision':'reject','note':'Synthetic evidence needs a corrected voucher'}))
        assert check(clients['owner'].get('/api/inventory/overview'))['items'][0]['value_piasters']==1725
        assert check(clients['clerk'].get('/api/inventory/writeoffs/queue'))['items'][0]['remaining_quantity']==1
        check(clients['clerk'].post('/api/inventory/writeoffs',headers=auth['clerk'],json={
            **draft,'quantity':1,'request_id':'g3g_writeoff_test_0003','evidence_ref':'G3G-DISPOSAL-003'}))
        from inventory import month_close_inventory_issue
        with connect() as db:
            assert 'تسوية' in month_close_inventory_issue(db,day[:7])
            try:
                db.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES (?,?,?)',
                           (day[:7],1,day))
            except sqlite3.IntegrityError:db.rollback()
            else:raise AssertionError('Direct month close ignored a pending inventory loss document')
            try:
                db.execute('''INSERT INTO inventory_return_writeoffs
                  (return_line_id,quantity,disposed_on,reason,evidence_ref,
                   physical_disposal_confirmed,created_by,created_at)
                  VALUES(?,?,?,?,?,1,?,?)''',
                  (return_line_id,3,day,'damaged','SYNTHETIC-OVERCAP-DIRECT',actors['clerk'],day))
            except sqlite3.IntegrityError:db.rollback()
            else:raise AssertionError('Raw SQLite insertion bypassed rejected-quantity limit')
        print('PASS G3G two-person rejected stock writeoffs, partial cap, immutable GL, privacy, revocation, patient cost and month-close gate')

if __name__=='__main__':run()
