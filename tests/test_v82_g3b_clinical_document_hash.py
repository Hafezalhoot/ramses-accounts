"""G3B document fingerprint: unauthorized/ref-only bypass must not issue protected revenue.

Fails if owner document opt-in isn't enforced, a clinician can forge a digest,
a document can be replaced post-witness, or source bytes enter finance SQLite.
Synthetic cases, users and bytes only.
"""
import hashlib
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PDF_A=b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF'
PDF_B=b'%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj\n%%EOF'


def run():
    with tempfile.TemporaryDirectory(prefix='g3b-hash-') as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner', RAMSES_ADMIN_PASSWORD='synthetic_g3b_owner_password')
        from bootstrap import connect, initialize
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner, medic, clerk, viewer, stranger = (TestClient(app) for _ in range(5))
        def ok(response, status=200):
            assert response.status_code == status,(status,response.status_code,response.text[:650])
            return response.json() if status==200 else None
        def login(client, name, password):
            return {'X-CSRF-Token': ok(client.post('/api/login',json={
                'username':name,'password':password}))['csrf']}
        oh=login(owner,'owner','synthetic_g3b_owner_password')
        roleids={}
        for name,role in [('medic_g3b','clinician'),('clerk_g3b','clerk'),('viewer_g3b','viewer')]:
            roleids[role]=ok(owner.post('/api/users',headers=oh,json={
                'username':name,'role':role,'password':'synthetic_g3b_employee_password'}))['id']
        mh=login(medic,'medic_g3b','synthetic_g3b_employee_password')
        ch=login(clerk,'clerk_g3b','synthetic_g3b_employee_password')
        login(viewer,'viewer_g3b','synthetic_g3b_employee_password')
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        deps=ok(owner.get('/api/lookups'))['departments']
        dept=next(d['id'] for d in deps if d['code']=='LAB')
        other=next(d['id'] for d in deps if d['code']=='RAD')
        point=next(p['id'] for p in ok(owner.get('/api/billing/config'))['points'] if p['kind']=='external')
        ok(owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={
            'user_id':roleids['clerk'],'active':True}))
        svc=ok(owner.post('/api/billing/services',headers=oh,json={
            'code':'G3BDOC','name':'Synthetic diagnostic specimen',
            'department_id':dept,'suggested_point':'external'}))['id']
        ok(owner.post(f'/api/billing/services/{svc}/prices',headers=oh,json={
            'valid_from':day,'amount':'75.00'}))
        pt=ok(clerk.post('/api/billing/patients',headers=ch,json={
            'display_name':'Synthetic test patient only','request_id':'g3b_patient_create_00000001'}))['id']
        case=ok(clerk.post('/api/billing/cases',headers=ch,json={
            'patient_id':pt,'kind':'outpatient','point_id':point,
            'business_date':day,'request_id':'g3b_case_open_00000001'}))['id']
        def line(s):
            return ok(clerk.post(f'/api/billing/cases/{case}/services',headers=ch,json={
                'service_id':svc,'quantity':1,'request_id':f'g3b_line_{s}_00000001'}))['id']
        identity={ 'user_id':roleids['clinician'], 'professional_name':'Synthetic Medical Test Operator',
            'registration_reference':'SYN-REG-TEST-ONLY-G3B',
            'review_note':'Synthetic review only, not professional licensing',
            'current_password':'synthetic_g3b_owner_password','approved':True}
        ok(owner.post('/api/billing/clinical/identity-review',headers=oh,json=identity))
        ok(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'department_id':dept,'user_id':roleids['clinician'],'active':True}))
        ok(owner.post(f'/api/billing/clinical/departments/{dept}/activate',headers=oh))
        # Avoid an irreversible policy that strands G3A reference-only witnesses
        # whose clinical statements are immutable and not yet invoiced.
        ok(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'department_id':other,'user_id':roleids['clinician'],'active':True}))
        ok(owner.post(f'/api/billing/clinical/departments/{other}/activate',headers=oh))
        legacy_case=ok(clerk.post('/api/billing/cases',headers=ch,json={
            'patient_id':pt,'kind':'outpatient','point_id':point,
            'business_date':day,'request_id':'g3b_old_case_open_0001'}))['id']
        legacy_service=ok(owner.post('/api/billing/services',headers=oh,json={
            'code':'G3BOLD','name':'Synthetic previous radiology',
            'department_id':other,'suggested_point':'external'}))['id']
        ok(owner.post(f'/api/billing/services/{legacy_service}/prices',headers=oh,json={
            'valid_from':day,'amount':'40.00'}))
        old_line=ok(clerk.post(f'/api/billing/cases/{legacy_case}/services',headers=ch,json={
            'service_id':legacy_service,'quantity':1,'request_id':'g3b_old_line_00001'}))['id']
        ok(medic.post(f'/api/billing/clinical/lines/{old_line}/attest',headers=mh,json={
            'evidence_reference':'SYN-G3A-OLD-PAPER-REF'}))
        ok(owner.post(f'/api/billing/clinical/departments/{other}/require-document',headers=oh,json={
            'current_password':'synthetic_g3b_owner_password'}),409)
        assert not any(x['department_id']==other for x in
                       ok(owner.get('/api/billing/clinical/policy'))['document_requirements'])
        protected=line('protected')
        requirement=f'/api/billing/clinical/departments/{dept}/require-document'
        ok(stranger.post(requirement,json={'current_password':'synthetic_g3b_owner_password'}),401)
        ok(medic.post(requirement,headers=mh,json={'current_password':'synthetic_g3b_owner_password'}),403)
        ok(owner.post(requirement,headers=oh,json={'current_password':'wrong-password'}),403)
        ok(owner.post(requirement,headers=oh,json={'current_password':'synthetic_g3b_owner_password'}))
        ok(owner.post(requirement,headers=oh,json={'current_password':'synthetic_g3b_owner_password'}),409)
        assert dept in [x['department_id'] for x in ok(owner.get('/api/billing/clinical/policy'))['document_requirements']]
        attest=f'/api/billing/clinical/lines/{protected}/attest'
        upload=f'/api/billing/clinical/lines/{protected}/attest-document'
        verify=f'/api/billing/clinical/lines/{protected}/verify-document'
        ok(medic.post(attest,headers=mh,json={'evidence_reference':'SYN-PAPER-REF-000001'}),409)
        ok(viewer.post(upload,headers={'X-CSRF-Token':'unknown'},data={'evidence_reference':'SYN-PAPER-REF-000001'},
                       files={'file':('report.pdf',PDF_A,'application/pdf')}),403)
        ok(medic.post(upload,headers=mh,data={'evidence_reference':'SYN-PAPER-REF-000001'},
                      files={'file':('report.txt',b'<script>alert(1)</script>','text/plain')}),400)
        ok(medic.post(upload,headers=mh,data={'evidence_reference':'SYN-PAPER-REF-000001'},
                      files={'file':('empty.pdf',b'','application/pdf')}),413)
        ok(medic.post(upload,headers=mh,data={'evidence_reference':'SYN-PAPER-REF-000001'},
                      files={'file':('big.pdf',b'%PDF-'+b'Z'*(6*1024*1024)+b'%%EOF','application/pdf')}),413)
        with connect() as c:
            # Even an SQL writer cannot bypass an owner-activated document requirement.
            c.execute("UPDATE billing_case_lines SET state='fulfilled',service_date=? WHERE id=?",(day,protected))
            try:
                c.execute('''INSERT INTO billing_clinical_attestations
                  (case_line_id,department_id,service_date,evidence_reference,attested_by,attested_at)
                  VALUES (?,?,?,?,?,?)''',(protected,dept,day,'SYN-FORGED-REFERENCE',roleids['clinician'],day))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Direct SQL accepted medical attestation without source hash')
            try:
                c.execute('''INSERT INTO billing_clinical_attestations
                  (case_line_id,department_id,service_date,evidence_reference,attested_by,attested_at,
                   document_sha256,document_size,document_media_type)
                  VALUES (?,?,?,?,?,?,?,?,?)''',
                  (protected,dept,day,'SYN-FORGED-REFERENCE',roleids['clinician'],day,'0'*64,0,'text/plain'))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Direct SQL accepted impossible hash metadata')
        digest=hashlib.sha256(PDF_A).hexdigest()
        witnessed=ok(medic.post(upload,headers=mh,data={'evidence_reference':'SYN-PAPER-REF-000001'},
                         files={'file':('PERSONAL_NAME_NOT_TO_PERSIST.pdf',PDF_A,'application/pdf')}))
        assert witnessed['document_sha256']==digest, witnessed
        assert witnessed['document_size']==len(PDF_A),witnessed
        assert witnessed['state']=='fulfilled'
        ok(medic.post(upload,headers=mh,data={'evidence_reference':'SYN-PAPER-REF-000001'},
                         files={'file':('report.pdf',PDF_A,'application/pdf')}),409)
        proof=ok(medic.get(f'/api/billing/clinical/lines/{protected}/evidence'))
        assert proof['document_sha256']==digest and proof['evidence_reference']=='SYN-PAPER-REF-000001'
        assert ok(medic.post(verify,headers=mh,files={'file':('original.pdf',PDF_A,'application/pdf')}))['matches'] is True
        assert ok(medic.post(verify,headers=mh,files={'file':('other.pdf',PDF_B,'application/pdf')}))['matches'] is False
        ok(owner.post(verify,headers=oh,files={'file':('report.pdf',PDF_A,'application/pdf')}),403)
        with connect() as c:
            row=c.execute('SELECT document_sha256,document_size,document_media_type FROM billing_clinical_attestations WHERE case_line_id=?',(protected,)).fetchone()
            assert tuple(row)==(digest,len(PDF_A),'application/pdf'),tuple(row)
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
            contents=c.execute('SELECT details FROM audit_log').fetchall()
            assert not any(digest in str(x[0]) or 'PERSONAL_NAME_NOT_TO_PERSIST' in str(x[0]) for x in contents)
            # No source document contents, patient-identifying filename, or independent document BLOB table.
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='billing_clinical_documents'").fetchone()
            try:c.execute('UPDATE billing_clinical_attestations SET document_sha256=? WHERE case_line_id=?',('f'*64,protected))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Clinical document hash mutable after witness')
        draft=ok(clerk.post(f'/api/billing/cases/{case}/drafts',headers=ch,json={
            'request_id':'g3b_draft_0000000001'}))
        assert draft['total_piasters']==7500,draft
        invoice=ok(clerk.post(f'/api/billing/drafts/{draft["id"]}/issue',headers=ch,json={
            'request_id':'g3b_issue_0000000001'}))
        assert invoice['amount_piasters']==7500,invoice
        # Once the grant is withdrawn, direct evidence access and verification are refused.
        ok(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'department_id':dept,'user_id':roleids['clinician'],'active':False}))
        ok(medic.get(f'/api/billing/clinical/lines/{protected}/evidence'),403)
        ok(medic.post(verify,headers=mh,files={'file':('report.pdf',PDF_A,'application/pdf')}),403)
        print('PASS G3B: immutable source fingerprint, protected invoice, one-way owner activation, revocation, no clinical bytes stored')


if __name__=='__main__':run()
