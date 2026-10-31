"""G2P: end-to-end, throwaway SQLite + real API calls, no patient data."""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as temp:
        os.environ.update(RAMSES_DB_PATH=str(Path(temp)/'sandbox.sqlite3'), RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='owner_2026_g2p_secure_password')
        from bootstrap import initialize, connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,clerk,reviewer,rogue=[TestClient(app) for _ in range(4)]
        def ok(resp,status=200):
            assert resp.status_code==status,(resp.status_code,resp.text,status)
            return resp.json() if status==200 else None
        def login(client,name,password):
            return {'X-CSRF-Token':ok(client.post('/api/login',json={'username':name,'password':password}))['csrf']}
        oh=login(owner,'owner','owner_2026_g2p_secure_password')
        ids={}
        for name,role in [('clerk_g2p','clerk'),('reviewer_g2p','reviewer'),('reviewer_rogue','reviewer')]:
            ids[name]=ok(owner.post('/api/users',headers=oh,json={
                'username':name,'role':role,'password':'g2p_secure_employee_password'}))['id']
        ch=login(clerk,'clerk_g2p','g2p_secure_employee_password')
        rh=login(reviewer,'reviewer_g2p','g2p_secure_employee_password')
        rogue_h=login(rogue,'reviewer_rogue','g2p_secure_employee_password')
        point=next(x for x in ok(owner.get('/api/billing/config'))['points'] if x['kind']=='internal')['id']
        for name in ('clerk_g2p','reviewer_g2p'):
            ok(owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={
                'user_id':ids[name],'active':True}))
        fund=ok(owner.post('/api/funds',headers=oh,json={'code':'g2p_till','name':'Internal settlement demo cash','kind':'cash'}))['id']
        ok(owner.post(f'/api/billing/points/{point}/cash-fund',headers=oh,json={'fund_id':fund}))
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        ok(clerk.post('/api/shifts/open',headers=ch,json={'business_date':day,'shift':'treasury','fund_id':fund}))
        dept=next(x['id'] for x in ok(owner.get('/api/lookups'))['departments'] if x['code']=='IPD')
        service=ok(owner.post('/api/billing/services',headers=oh,json={
            'code':'G2P_STAY_SAMPLE','name':'Fictional inpatient service','department_id':dept}))['id']
        ok(owner.post(f'/api/billing/services/{service}/prices',headers=oh,json={'valid_from':day,'amount':'480'}))
        patient=ok(clerk.post('/api/billing/patients',headers=ch,json={
            'display_name':'Synthetic inpatient case','request_id':'g2p_patient_create_0001'}))
        case=ok(clerk.post('/api/billing/cases',headers=ch,json={
            'patient_id':patient['id'],'point_id':point,'kind':'inpatient',
            'business_date':day,'request_id':'g2p_case_create_00001'}))['id']
        base=f'/api/case-settlement/cases/{case}'
        pre=ok(clerk.get(base))['preflight']
        assert not pre['ready'] and not pre['invoice_count']
        ok(clerk.post(base+'/request',headers=ch,json={
            'request_id':'g2p_clearance_early1','evidence_reference':'TEST-DISCHARGE-001',
            'note':'Attempt to close a case without an invoice'}),409)
        line=ok(clerk.post(f'/api/billing/cases/{case}/services',headers=ch,json={
            'service_id':service,'quantity':1,'request_id':'g2p_service_create_0001'}))['id']
        pre=ok(clerk.get(base))['preflight']
        assert pre['ordered_services']==1 and not pre['ready']
        ok(reviewer.post(f'/api/billing/lines/{line}/fulfill',headers=rh))
        draft=ok(clerk.post(f'/api/billing/cases/{case}/drafts',headers=ch,json={
            'request_id':'g2p_draft_create_00001'}))['id']
        pre=ok(clerk.get(base))['preflight']
        assert pre['fulfilled_unbilled']==1 and pre['unissued_drafts']==1
        invoice=ok(clerk.post(f'/api/billing/drafts/{draft}/issue',headers=ch,json={
            'request_id':'g2p_invoice_create_001'}))['id']
        pre=ok(clerk.get(base))['preflight']
        assert pre['outstanding_piasters']==48000 and not pre['ready']
        ok(clerk.post(f'/api/billing/cases/{case}/collect',headers=ch,json={
            'request_id':'g2p_collection_00001','point_id':point,'invoice_id':invoice,
            'parts':[{'method':'cash','amount':'480'}]}))
        pre=ok(clerk.get(base))['preflight']
        assert pre['ready'] and pre['outstanding_piasters']==0,pre
        request_payload={'request_id':'g2p_clearance_request_1','evidence_reference':'TEST-DISCHARGE-001',
                         'note':'Clinical release separately documented by team'}
        submitted=ok(clerk.post(base+'/request',headers=ch,json=request_payload))
        assert submitted['status']=='pending'
        assert ok(clerk.post(base+'/request',headers=ch,json=request_payload))['replayed']
        # A late credit request invalidates a submitted clearance until it is reviewed.
        pending_credit=ok(clerk.post(f'/api/billing/cases/{case}/credits',headers=ch,json={
            'invoice_id':invoice,'amount':'10','reason':'Synthetic financial correction requested after readiness',
            'request_id':'g2p_credit_pending_001'}))['id']
        blocked=reviewer.post(f'/api/case-settlement/requests/{submitted["id"]}/decision',
            headers=rh,json={'decision':'approve','note':'Must recheck all pending credits'})
        assert blocked.status_code==409,blocked.text
        ok(reviewer.post(f'/api/billing/credits/{pending_credit}/decision',headers=rh,
            json={'decision':'reject','note':'Test scenario declines the later credit'}))
        # Revoking a point during review must invalidate the reviewer session instantly.
        ok(owner.post(f'/api/billing/points/{point}/assign',headers=oh,
            json={'user_id':ids['reviewer_g2p'],'active':False}))
        assert reviewer.post(f'/api/case-settlement/requests/{submitted["id"]}/decision',
            headers=rh,json={'decision':'approve','note':'Cannot approve after grant revoked'}).status_code==403
        ok(owner.post(f'/api/billing/points/{point}/assign',headers=oh,
            json={'user_id':ids['reviewer_g2p'],'active':True}))
        assert rogue.get(base).status_code==403
        assert rogue.post(f'/api/case-settlement/requests/{submitted["id"]}/decision',headers=rogue_h,
                          json={'decision':'approve','note':'Attempt from another station'}).status_code==403
        assert clerk.post(f'/api/case-settlement/requests/{submitted["id"]}/decision',headers=ch,
                          json={'decision':'approve','note':'Attempt self approval'}).status_code==403
        assert reviewer.post(f'/api/case-settlement/requests/{submitted["id"]}/decision',headers=rh,
                          json={'decision':'approve','note':'Maker cannot self approve'}).status_code==200
        # Reviewer after closure cannot approve the same request or reopen the case.
        assert reviewer.post(f'/api/case-settlement/requests/{submitted["id"]}/decision',headers=rh,
                             json={'decision':'approve','note':'Try to approve twice'}).status_code==409
        after=ok(clerk.get(f'/api/billing/cases/{case}'))
        assert after['case']['status']=='closed'
        assert clerk.post(f'/api/billing/cases/{case}/services',headers=ch,json={
            'service_id':service,'quantity':1,'request_id':'g2p_closed_service_01'}).status_code==409
        assert clerk.post(f'/api/billing/cases/{case}/credits',headers=ch,json={
            'invoice_id':invoice,'amount':'1','reason':'Post-close attempt to alter the patient charge',
            'request_id':'g2p_closed_credit_0001'}).status_code==409
        assert clerk.post(f'/api/billing/cases/{case}/apply-advance',headers=ch,json={
            'invoice_id':invoice,'amount':'1',
            'request_id':'g2p_closed_advance_01'}).status_code==409
        with connect() as c:
            assert c.execute("SELECT count(*) FROM billing_case_clearance_requests WHERE status='approved'").fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM gl_journals').fetchone()[0]>=1
            try:
                c.execute("UPDATE billing_cases SET status='open' WHERE id=?",(case,))
                raise AssertionError('Reopened a closed case')
            except __import__('sqlite3').IntegrityError:
                pass
            for sql,args in (
                ("UPDATE billing_cases SET default_point_id=? WHERE id=?",(point,case)),
                ("DELETE FROM billing_cases WHERE id=?",(case,)),
                ("DELETE FROM billing_case_lines WHERE id=?",(line,)),
            ):
                try:
                    c.execute(sql,args)
                    raise AssertionError('Closed-case audit protection bypassed: '+sql)
                except __import__('sqlite3').IntegrityError:
                    pass
            original_collection=c.execute('SELECT id FROM billing_collections WHERE case_id=?',(case,)).fetchone()[0]
            original_part=c.execute('SELECT * FROM billing_payment_parts WHERE collection_id=?',(original_collection,)).fetchone()
            try:
                c.execute("INSERT INTO billing_payment_parts(collection_id,method,fund_id,voucher_id,amount_piasters) VALUES (?,?,?,?,?)",(original_collection,original_part['method'],original_part['fund_id'],
                  original_part['voucher_id'],original_part['amount_piasters']))
                raise AssertionError('Inserted payment split to closed case')
            except __import__('sqlite3').IntegrityError:
                pass
            try:
                c.execute("DELETE FROM billing_case_clearance_requests WHERE id=?",(submitted['id'],))
                raise AssertionError('Deleted approved clearance')
            except __import__('sqlite3').IntegrityError:
                pass
            c.rollback()
        # No-charge financial case cancellation cannot fabricate an invoice, collection or GL.
        nocharge_case=ok(owner.post('/api/billing/cases',headers=oh,json={
            'patient_id':patient['id'],'point_id':point,'kind':'nicu',
            'business_date':day,'request_id':'g2p_no_charge_case_01'}))['id']
        nocharge_base=f'/api/case-settlement/cases/{nocharge_case}'
        assert ok(owner.get(nocharge_base))['preflight']['no_charge_ready']
        nocharge_payload={'request_id':'g2p_cancel_zero_charge_01','mode':'no_charge',
                          'evidence_reference':'TEST-CANCEL-ADMISSION-01',
                          'note':'No services provided and no patient money received'}
        assert clerk.post(nocharge_base+'/request',headers=ch,json=nocharge_payload).status_code==403
        with connect() as c:
            journals_before=c.execute('SELECT count(*) FROM gl_journals').fetchone()[0]
            cash_before=c.execute('SELECT count(*) FROM fund_movements').fetchone()[0]
        cancelled=ok(owner.post(nocharge_base+'/request',headers=oh,json=nocharge_payload))
        assert cancelled['status']=='pending'
        assert owner.post(f'/api/case-settlement/requests/{cancelled["id"]}/decision',headers=oh,
                          json={'decision':'approve','note':'Cannot sign off own no-charge request'}).status_code==403
        ok(reviewer.post(f'/api/case-settlement/requests/{cancelled["id"]}/decision',headers=rh,
                         json={'decision':'approve','note':'No financial activity verified independently'}))
        assert ok(owner.get(nocharge_base))['requests'][0]['clearance_mode']=='no_charge'
        assert ok(owner.get(f'/api/billing/cases/{nocharge_case}'))['case']['status']=='closed'
        with connect() as c:
            assert c.execute('SELECT count(*) FROM gl_journals').fetchone()[0]==journals_before
            assert c.execute('SELECT count(*) FROM fund_movements').fetchone()[0]==cash_before
        # A service added after the request, before review, invalidates no-charge approval.
        stale_case=ok(owner.post('/api/billing/cases',headers=oh,json={
            'patient_id':patient['id'],'point_id':point,'kind':'operation',
            'business_date':day,'request_id':'g2p_no_charge_stale_case_01'}))['id']
        stale_base=f'/api/case-settlement/cases/{stale_case}'
        stale=ok(owner.post(stale_base+'/request',headers=oh,json={
            **nocharge_payload,'request_id':'g2p_cancel_zero_charge_02'}))['id']
        ok(clerk.post(f'/api/billing/cases/{stale_case}/services',headers=ch,json={
            'service_id':service,'quantity':1,'request_id':'g2p_stale_case_service_01'}))
        assert reviewer.post(f'/api/case-settlement/requests/{stale}/decision',headers=rh,
            json={'decision':'approve','note':'Must reject changes during review'}).status_code==409
        ok(reviewer.post(f'/api/case-settlement/requests/{stale}/decision',headers=rh,
            json={'decision':'reject','note':'Treatment started after cancellation requested'}))
        assert ok(owner.get(f'/api/billing/cases/{stale_case}'))['case']['status']=='open'
        # Two independent reviewers must never create two close decisions.
        from concurrent.futures import ThreadPoolExecutor
        ok(owner.post(f'/api/billing/points/{point}/assign',headers=oh,
            json={'user_id':ids['reviewer_rogue'],'active':True}))
        parallel_case=ok(owner.post('/api/billing/cases',headers=oh,json={
            'patient_id':patient['id'],'point_id':point,'kind':'nicu',
            'business_date':day,'request_id':'g2p_parallel_cancel_case'}))['id']
        parallel_request=ok(owner.post(f'/api/case-settlement/cases/{parallel_case}/request',headers=oh,json={
            **nocharge_payload,'request_id':'g2p_parallel_cancel_request'}))['id']
        def decide_parallel(client,head):
            return client.post(f'/api/case-settlement/requests/{parallel_request}/decision',
                headers=head,json={'decision':'approve','note':'Checked zero-activity financial case'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(decide_parallel,reviewer,rh)
            second=pool.submit(decide_parallel,rogue,rogue_h)
            statuses=sorted((first.result(),second.result()))
        assert statuses==[200,409],statuses
        with connect() as c:
            assert c.execute('SELECT count(*) FROM billing_case_clearance_requests WHERE id=? AND status="approved"',
                (parallel_request,)).fetchone()[0]==1
            assert c.execute('SELECT status FROM billing_cases WHERE id=?',(parallel_case,)).fetchone()[0]=='closed'
        print('PASS: ready, invoice, financial close maker/checker, no-charge, concurrent approval, immutable closure')


if __name__=='__main__':run()
