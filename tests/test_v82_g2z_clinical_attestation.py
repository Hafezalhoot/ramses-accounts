"""G2Z: independent per-department attestation cannot be forged by finance actors.

The break this test catches: financial 'fulfill' or invoice issuance bypassing
an activated clinical policy, and a revoked attestor still signing evidence.
Synthetic API users/cases only. No hospital clinical/financial records.
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
    with tempfile.TemporaryDirectory(prefix='g2z-clinical-') as temp:
        os.environ.update(RAMSES_DB_PATH=str(Path(temp)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_g2z_owner_password_long')
        from bootstrap import initialize, connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner, reviewer, clerk, medic, stranger, outsider = (TestClient(app) for _ in range(6))

        def check(r,status=200):
            assert r.status_code==status, (status,r.status_code,r.text[:900])
            return r.json() if status==200 else None
        def login(client,username,password):
            return {'X-CSRF-Token':check(client.post('/api/login',json={
                'username':username,'password':password}))['csrf']}

        oh=login(owner,'owner','synthetic_g2z_owner_password_long')
        actors={}
        for name,role in [('g2z_reviewer','reviewer'),('g2z_clerk','clerk'),
                          ('g2z_medic','clinician'),('g2z_outsider','viewer')]:
            actors[name]=check(owner.post('/api/users',headers=oh,json={
                'username':name,'role':role,'password':'synthetic_staff_password_g2z'}))['id']
        rh=login(reviewer,'g2z_reviewer','synthetic_staff_password_g2z')
        ch=login(clerk,'g2z_clerk','synthetic_staff_password_g2z')
        mh=login(medic,'g2z_medic','synthetic_staff_password_g2z')
        sh=login(stranger,'g2z_outsider','synthetic_staff_password_g2z')
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        dept=next(d['id'] for d in check(owner.get('/api/lookups'))['departments'] if d['code']=='LAB')
        other_dept=next(d['id'] for d in check(owner.get('/api/lookups'))['departments'] if d['code']=='IPD')
        point=next(p['id'] for p in check(owner.get('/api/billing/config'))['points'] if p['kind']=='external')
        for name in ('g2z_clerk','g2z_reviewer'):
            check(owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={
                'user_id':actors[name],'active':True}))
        service=check(owner.post('/api/billing/services',headers=oh,json={
            'code':'G2Z_LAB','name':'Synthetic G2Z clinical service',
            'department_id':dept,'suggested_point':'external'}))['id']
        check(owner.post(f'/api/billing/services/{service}/prices',headers=oh,json={
            'valid_from':day,'amount':'90.00'}))
        patient=check(clerk.post('/api/billing/patients',headers=ch,json={
            'display_name':'Synthetic patient for G2Z only','request_id':'g2z_patient_record_0001'}))['id']
        case=check(clerk.post('/api/billing/cases',headers=ch,json={
            'patient_id':patient,'kind':'outpatient','point_id':point,
            'business_date':day,'request_id':'g2z_patient_case_0001'}))['id']
        def add_line(suffix):
            return check(clerk.post(f'/api/billing/cases/{case}/services',headers=ch,json={
                'service_id':service,'quantity':1,'request_id':f'g2z_line_unique_{suffix}_0001'}))['id']

        # An already-fulfilled clinical line and an already prepared draft may
        # exist before the owner activates the policy: issue-time checks matter.
        old_line=add_line('legacy')
        check(reviewer.post(f'/api/billing/lines/{old_line}/fulfill',headers=rh))
        old_draft=check(clerk.post(f'/api/billing/cases/{case}/drafts',headers=ch,json={
            'request_id':'g2z_pre_activation_draft_0001'}))['id']

        grant={'user_id':actors['g2z_medic'],'department_id':dept,'active':True}
        check(outsider.get('/api/billing/clinical/queue'),401)
        check(clerk.post('/api/billing/clinical/grants',headers=ch,json=grant),403)
        check(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'user_id':actors['g2z_reviewer'],'department_id':dept,'active':True}),400)
        check(owner.post('/api/billing/clinical/identity-review',headers=oh,json={
            'user_id':actors['g2z_medic'], 'professional_name':'Synthetic clinical account',
            'registration_reference':'SYNTHETIC-G2Z-REGISTRATION-0001',
            'review_note':'Synthetic manual review for regression testing',
            'current_password':'synthetic_g2z_owner_password_long','approved':True}))
        check(owner.post('/api/billing/clinical/grants',headers=oh,json=grant))
        # An assigned account cannot sign or change clinical billing state
        # before the owner explicitly turns on the departmental pilot.
        check(medic.post(f'/api/billing/clinical/lines/{old_line}/attest',headers=mh,json={
            'evidence_reference':'SYN-EARLY-WITNESS-REF'}),409)
        with connect() as c:
            try:
                c.execute('''INSERT INTO billing_clinical_attestations
                    (case_line_id,department_id,service_date,evidence_reference,attested_by,attested_at)
                    VALUES (?,?,?,?,?,?)''',
                    (old_line,dept,day,'SYN-EARLY-DIRECT-REF',actors['g2z_medic'],day))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Unsigned inactive clinical policy accepted a direct DB witness')
        check(owner.post(f'/api/billing/clinical/departments/{dept}/activate',headers=oh))
        check(owner.post(f'/api/billing/clinical/departments/{dept}/activate',headers=oh),409)
        check(stranger.get('/api/billing/clinical/policy'),403)
        # The granted viewer has no financial privilege, nor rights in another dept.
        check(medic.get('/api/billing/cases'),403)
        check(medic.get('/api/billing/clinical/queue'))
        check(stranger.get('/api/billing/clinical/queue'),403)
        check(medic.post(f'/api/billing/lines/{old_line}/fulfill',headers=mh),403)
        check(clerk.post(f'/api/billing/drafts/{old_draft}/issue',headers=ch,json={
            'request_id':'g2z_pre_activation_issue_0001'}),409)
        check(owner.post(f'/api/billing/clinical/lines/{old_line}/attest',headers=oh,json={
            'evidence_reference':'SYN-G2Z-CLINICAL-0001'}),403)
        check(reviewer.post(f'/api/billing/clinical/lines/{old_line}/attest',headers=rh,json={
            'evidence_reference':'SYN-G2Z-CLINICAL-0001'}),403)
        check(stranger.post(f'/api/billing/clinical/lines/{old_line}/attest',headers=sh,json={
            'evidence_reference':'SYN-G2Z-CLINICAL-0001'}),403)
        check(medic.post(f'/api/billing/clinical/lines/{old_line}/attest',headers=mh,json={
            'evidence_reference':'bad'}),422)
        evidence_old=check(medic.post(f'/api/billing/clinical/lines/{old_line}/attest',headers=mh,json={
            'evidence_reference':'SYN-G2Z-CLINICAL-0001'}))
        assert evidence_old['state']=='fulfilled' and evidence_old['attested_by']==actors['g2z_medic']
        check(medic.post(f'/api/billing/clinical/lines/{old_line}/attest',headers=mh,json={
            'evidence_reference':'SYN-G2Z-CLINICAL-0001'}),409)
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM billing_invoices').fetchone()[0]==0, 'Missing clinical proof posted revenue'
        invoice=check(clerk.post(f'/api/billing/drafts/{old_draft}/issue',headers=ch,json={
            'request_id':'g2z_pre_activation_issue_0002'}))
        assert invoice['amount_piasters']==9000

        new_line=add_line('enforced')
        check(owner.post(f'/api/billing/lines/{new_line}/fulfill',headers=oh),403)
        check(reviewer.post(f'/api/billing/lines/{new_line}/fulfill',headers=rh),403)
        check(clerk.post(f'/api/billing/lines/{new_line}/fulfill',headers=ch),403)
        # Live revocation denies the *next* attestation without session logout.
        check(owner.post('/api/billing/clinical/grants',headers=oh,json={**grant,'active':False}))
        check(medic.post(f'/api/billing/clinical/lines/{new_line}/attest',headers=mh,json={
            'evidence_reference':'SYN-G2Z-CLINICAL-0002'}),403)
        check(owner.post('/api/billing/clinical/grants',headers=oh,json=grant))
        pending=check(medic.get('/api/billing/clinical/queue'))['items']
        assert any(item['line_id']==new_line for item in pending),pending
        assert all('unit_price_piasters' not in item and 'display_name' not in item for item in pending)
        check(stranger.get('/api/billing/clinical/queue'),403)
        check(stranger.get('/api/billing/clinical/queue'),403)
        check(medic.post(f'/api/billing/clinical/lines/{new_line}/attest',headers=mh,json={
            'evidence_reference':'SYN-G2Z-CLINICAL-0002'}))
        guard_line=add_line('guard_not_executed')
        with connect() as c:
            row=c.execute('SELECT service_date,fulfilled_by,state FROM billing_case_lines WHERE id=?',(new_line,)).fetchone()
            assert row['state']=='fulfilled' and row['fulfilled_by']==actors['g2z_medic'] and row['service_date']==day,dict(row)
            record=c.execute('SELECT attested_by,evidence_reference,service_date FROM billing_clinical_attestations WHERE case_line_id=?',(new_line,)).fetchone()
            assert record['evidence_reference']=='SYN-G2Z-CLINICAL-0002' and record['service_date']==day and record['attested_by']==actors['g2z_medic'],dict(record)
            try:
                c.execute('UPDATE billing_clinical_attestations SET evidence_reference=? WHERE case_line_id=?',('FORGED',new_line))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Clinical evidence could be changed directly in SQLite')
            try:c.execute('DELETE FROM billing_clinical_attestations WHERE case_line_id=?',(new_line,))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Clinical evidence could be deleted directly in SQLite')
            assert c.execute('SELECT COUNT(*) FROM billing_clinical_attestations').fetchone()[0]==2
            assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='clinical_service_attested'").fetchone()[0]==2
            assert not any('SYN-G2Z-CLINICAL' in row[0] for row in c.execute(
                "SELECT details FROM audit_log WHERE action='clinical_service_attested'")), (
                'Clinical source document references must not leak to general audit/Google sync')
            try:c.execute('DELETE FROM billing_clinical_policies WHERE department_id=?',(dept,))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Department clinical protection could be silently disabled')
            # Server-side constraints must reject a mismatched clinical department
            # even from a developer who accidentally bypasses the API.
            try:
                c.execute('''INSERT INTO billing_clinical_attestations
                     (case_line_id,department_id,service_date,evidence_reference,attested_by,attested_at)
                     VALUES (?,?,?,?,?,?)''',(guard_line,other_dept,day,'SYN-FORGED-DEPT',actors['g2z_medic'],day))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Duplicate/mismatched clinical statement accepted')
        draft=check(clerk.post(f'/api/billing/cases/{case}/drafts',headers=ch,json={
            'request_id':'g2z_enforced_invoice_draft_0001'}))
        assert draft['total_piasters']==9000
        check(clerk.post(f'/api/billing/drafts/{draft["id"]}/issue',headers=ch,json={
            'request_id':'g2z_enforced_invoice_issue_001'}))
        check(medic.post(f'/api/billing/clinical/lines/{new_line}/attest',headers=mh,json={
            'evidence_reference':'SYN-G2Z-CLINICAL-0002'}),409)
        # No policy toggle-off and no cross-department attestation.
        assert check(owner.get('/api/billing/clinical/policy'))['departments'][0]['department_id']==dept
        assert other_dept!=dept
        print('PASS G2Z: independent department clinical witness, invoice gate, immutable proof, live revocation')

if __name__=='__main__':
    run()
