"""G3F: a financially approved physical return is *not* reusable stock before a clinical release.

Independent literal-value FastAPI/SQLite test, synthetic identities, no real patients.
Mutation targets: count pending returns in FIFO; let a finance role release; bypass SQL guard;
ignore live clinical grant revocation; double-sign or edit inspection; change source GL.
"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3f-quarantine-') as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp)/'synthetic.sqlite3'),
            RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_g3f_owner_secret')
        for k in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(k,None)
        from bootstrap import connect,initialize
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,clerk,reviewer,clinician,outsider=(TestClient(app) for _ in range(5))
        def check(response,status=200):
            assert response.status_code==status,(status,response.status_code,response.text[:600])
            return response.json() if status==200 else None
        def auth(client,name,pw):
            return {'X-CSRF-Token':check(client.post('/api/login',json={'username':name,'password':pw}))['csrf']}
        oh=auth(owner,'owner','synthetic_g3f_owner_secret')
        actors={}
        for name,role in (('g3f_clerk','clerk'),('g3f_reviewer','reviewer'),
                          ('g3f_clinician','clinician'),('g3f_other_clinician','clinician')):
            actors[name]=check(owner.post('/api/users',headers=oh,json={
                'username':name,'password':'synthetic_g3f_actor_secret','role':role}))['id']
        ch=auth(clerk,'g3f_clerk','synthetic_g3f_actor_secret')
        rh=auth(reviewer,'g3f_reviewer','synthetic_g3f_actor_secret')
        mh=auth(clinician,'g3f_clinician','synthetic_g3f_actor_secret')
        auth(outsider,'g3f_other_clinician','synthetic_g3f_actor_secret')
        for name in ('g3f_clerk','g3f_reviewer'):
            check(owner.post('/api/inventory/access',headers=oh,json={
                'user_id':actors[name], 'can_prepare':name=='g3f_clerk',
                'can_approve':name=='g3f_reviewer', 'reason':'Synthetic stock segregation authorization'}))
        dept=next(x['id'] for x in check(owner.get('/api/lookups'))['departments'] if x['code']=='OR')
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        point=next(x['id'] for x in check(owner.get('/api/billing/config'))['points'] if x['kind']=='internal')
        for name in ('g3f_clerk','g3f_reviewer'):
            check(owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={
                'user_id':actors[name],'active':True}))
        patient=check(owner.post('/api/billing/patients',headers=oh,json={
            'display_name':'Synthetic G3F patient','request_id':'g3f_patient_0001'}))['id']
        case=check(owner.post('/api/billing/cases',headers=oh,json={
            'patient_id':patient,'point_id':point,'kind':'operation','business_date':day,
            'request_id':'g3f_case_test_0001'}))['id']
        vendor=check(owner.post('/api/inventory/vendors',headers=oh,json={
            'code':'G3F_VENDOR','name':'Synthetic audited medical vendor'}))['id']
        item=check(owner.post('/api/inventory/items',headers=oh,json={
            'code':'G3F_SUPPLY','name':'Synthetic reusable demo supply', 'unit':'piece'}))['id']
        receipt=check(clerk.post('/api/inventory/receipts',headers=ch,json={
            'vendor_id':vendor,'received_on':day,'invoice_ref':'G3F-SUPPLIER-INVOICE',
            'evidence_ref':'G3F-GOODS-RECEIPT', 'request_id':'g3f_receipt_0001',
            'lines':[{'item_id':item,'quantity':2,'unit_cost':'12.00',
                      'batch_ref':'G3F-LOT-A'}]}))['id']
        check(reviewer.post(f'/api/inventory/receipts/{receipt}/decision',headers=rh,json={
            'decision':'approve','note':'Synthetic independent delivery authorization'}))
        issue=check(clerk.post('/api/inventory/issues',headers=ch,json={
            'department_id':dept,'case_id':case,'used_on':day,
            'evidence_ref':'G3F-CONSUMPTION-ORIGINAL','request_id':'g3f_issue_test_0001',
            'lines':[{'item_id':item,'quantity':2}]}))['id']
        check(reviewer.post(f'/api/inventory/issues/{issue}/decision',headers=rh,json={
            'decision':'approve','note':'Synthetic reviewed original FIFO consumption'}))
        allocation=check(clerk.get(f'/api/inventory/issues/{issue}/returnable',headers=ch))['allocations'][0]['issue_allocation_id']
        ret=check(clerk.post('/api/inventory/returns',headers=ch,json={
            'issue_id':issue,'returned_on':day,'evidence_ref':'G3F-PHYSICAL-RETURN-ONE',
            'request_id':'g3f_return_test_0001','lines':[{'issue_allocation_id':allocation,'quantity':1}]}))['id']
        financial=check(reviewer.post(f'/api/inventory/returns/{ret}/decision',headers=rh,json={
            'decision':'approve','note':'Synthetic independent financial inventory return'}))
        assert financial['cost_piasters']==1200
        stock=check(owner.get('/api/inventory/overview'))['items'][0]
        assert (stock['quantity_on_hand'],stock['quarantined_quantity'],stock['available_quantity'])==(1,1,0),stock
        assert stock['value_piasters']==1200
        assert check(owner.get(f'/api/inventory/cases/{case}/cost'))['total_returned_piasters']==1200
        assert check(owner.get('/api/inventory/reconciliation',params={'period':day[:7]}))['matched']
        assert check(owner.get('/api/inventory/reconciliation',params={'period':day[:7]}))['quarantined_quantity']==1

        candidate=check(clerk.post('/api/inventory/issues',headers=ch,json={
            'department_id':dept,'case_id':case,'used_on':day,
            'evidence_ref':'G3F-SECOND-ISSUE-REQUIRES-RELEASE',
            'request_id':'g3f_issue_test_0002','lines':[{'item_id':item,'quantity':1}]}))['id']
        check(reviewer.post(f'/api/inventory/issues/{candidate}/decision',headers=rh,json={
            'decision':'approve','note':'Should fail pending clinical release'}),409)
        with connect() as db:
            assert db.execute('SELECT status FROM inventory_issues WHERE id=?',(candidate,)).fetchone()[0]=='pending'
            assert db.execute('SELECT count(*) FROM inventory_issue_allocations WHERE issue_id=?',(candidate,)).fetchone()[0]==0
            journals=db.execute('SELECT count(*) FROM gl_journals').fetchone()[0]
            # Guard must work even if an attacker skips the API's FIFO allocator.
            line=db.execute('SELECT id FROM inventory_issue_lines WHERE issue_id=?',(candidate,)).fetchone()[0]
            lot=db.execute('SELECT id FROM inventory_receipt_lines WHERE receipt_id=?',(receipt,)).fetchone()[0]
            try:
                db.execute('''INSERT INTO inventory_issue_allocations(issue_id,issue_line_id,receipt_line_id,quantity,cost_piasters)
                     VALUES(?,?,?,?,?)''',(candidate,line,lot,1,1200))
            except sqlite3.IntegrityError:
                db.rollback()
            else:raise AssertionError('Direct SQL reused quarantined patient return')
            assert db.execute('SELECT count(*) FROM gl_journals').fetchone()[0]==journals

        # No clinician approval from a financial role; no identity/grant, no queue.
        check(owner.get('/api/inventory/inspections/queue'),403)
        check(reviewer.post('/api/inventory/inspections/1/decision',headers=rh,json={
            'decision':'release','inspected_on':day,'evidence_ref':'FRAUDULENT-RELEASE',
            'note':'Financial role pretending to medically inspect'}),403)
        check(clinician.get('/api/inventory/inspections/queue'),403)
        identity={'user_id':actors['g3f_clinician'],'professional_name':'Synthetic G3F Medical Reviewer',
            'registration_reference':'SYN-CLINICIAN-REVIEW-2026', 'review_note':'Synthetic credentials manually reviewed in test only',
            'approved':True,'current_password':'synthetic_g3f_owner_secret'}
        check(owner.post('/api/billing/clinical/identity-review',headers=oh,json=identity))
        check(clinician.get('/api/inventory/inspections/queue'),403)
        check(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'user_id':actors['g3f_clinician'],'department_id':dept,'active':True}))
        queue=check(clinician.get('/api/inventory/inspections/queue'))['items']
        assert len(queue)==1 and queue[0]['return_id']==ret,queue
        assert not {'case_id','case_no','patient_code','patient_name','unit_cost_piasters','value_piasters'} & set(queue[0]),queue
        row_id=queue[0]['return_line_id']
        decision={'decision':'release','inspected_on':day,'evidence_ref':'G3F-INFECTION-CONTROL-CLEARANCE-001',
            'note':'Synthetic source verified unused, intact and cleared',
            'unused_confirmed':True,'packaging_intact':True,'infection_control_clearance':True}
        check(clinician.post(f'/api/inventory/inspections/{row_id}/decision',headers=mh,
            json={**decision,'infection_control_clearance':False}),409)
        check(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'user_id':actors['g3f_clinician'],'department_id':dept,'active':False}))
        check(clinician.post(f'/api/inventory/inspections/{row_id}/decision',headers=mh,json=decision),403)
        check(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'user_id':actors['g3f_clinician'],'department_id':dept,'active':True}))
        approved=check(clinician.post(f'/api/inventory/inspections/{row_id}/decision',headers=mh,json=decision))
        assert approved['status']=='released',approved
        assert check(clinician.get('/api/inventory/inspections/queue'))['items']==[]
        check(clinician.post(f'/api/inventory/inspections/{row_id}/decision',headers=mh,json=decision),409)
        with connect() as db:
            for sql in ('UPDATE inventory_return_inspections SET decision=\'rejected\' WHERE return_line_id=?',
                        'DELETE FROM inventory_return_inspections WHERE return_line_id=?'):
                try:db.execute(sql,(row_id,))
                except sqlite3.IntegrityError:db.rollback()
                else:raise AssertionError('Clinical inspection evidence is mutable')
        assert check(owner.get('/api/inventory/overview'))['items'][0]['available_quantity']==1
        post=check(reviewer.post(f'/api/inventory/issues/{candidate}/decision',headers=rh,json={
            'decision':'approve','note':'Release is now independently clinically signed'}))
        assert post['cost_piasters']==1200,post
        assert check(owner.get('/api/inventory/reconciliation',params={'period':day[:7]}))['matched']
        # Second return from same original allocation is clinically REJECTED. It is
        # counted in owned GL, but must never be available again.
        ret2=check(clerk.post('/api/inventory/returns',headers=ch,json={
            'issue_id':issue,'returned_on':day,'evidence_ref':'G3F-PHYSICAL-RETURN-TWO',
            'request_id':'g3f_return_test_0002','lines':[{'issue_allocation_id':allocation,'quantity':1}]}))['id']
        check(reviewer.post(f'/api/inventory/returns/{ret2}/decision',headers=rh,json={
            'decision':'approve','note':'Second independent financial return document'}))
        pending=check(clinician.get('/api/inventory/inspections/queue'))['items']
        assert len(pending)==1 and pending[0]['return_id']==ret2,pending
        check(clinician.post(f'/api/inventory/inspections/{pending[0]["return_line_id"]}/decision',headers=mh,
            json={'decision':'reject','inspected_on':day,'evidence_ref':'G3F-DAMAGED-UNIT-PROOF',
                  'note':'Synthetic physically compromised packaging; no reuse allowed'}))
        stock=check(owner.get('/api/inventory/overview'))['items'][0]
        assert (stock['quantity_on_hand'],stock['quarantined_quantity'],stock['available_quantity'])==(1,1,0),stock
        assert check(owner.get('/api/inventory/reconciliation',params={'period':day[:7]}))['matched']
        assert check(owner.get(f'/api/inventory/cases/{case}/cost'))['total_returned_piasters']==2400
        with connect() as db:
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        print('PASS G3F return quarantine, independent licensed-manual-role pilot, FIFO SQL guard, immutable inspection, live revocation, GL unchanged')

if __name__=='__main__':run()
