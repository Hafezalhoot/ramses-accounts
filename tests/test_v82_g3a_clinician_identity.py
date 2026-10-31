"""G3A independent clinician role: no viewer/finance inheritance, owner-reviewed identity.

Mutation caught: accept a viewer as witness, or allow clinician into one financial API,
create clinician without credential review, or allow a revoked clinician to sign.
All records are synthetic and stored in an isolated SQLite file.
"""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory(prefix='g3a-clinician-') as temp:
        os.environ.update(RAMSES_DB_PATH=str(Path(temp)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_clinician_owner_secret_2026')
        from bootstrap import connect, initialize
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner, clinician, viewer = (TestClient(app) for _ in range(3))

        def check(response, status=200):
            assert response.status_code == status, (status, response.status_code, response.text[:500])
            return response.json() if status == 200 else None

        def login(client, name, password):
            result=check(client.post('/api/login',json={'username':name,'password':password}))
            return {'X-CSRF-Token': result['csrf']}

        oh=login(owner,'owner','synthetic_clinician_owner_secret_2026')
        cid=check(owner.post('/api/users',headers=oh,json={
            'username':'synthetic_clinician','password':'synthetic_clinician_password_2026',
            'role':'clinician'}))['id']
        vid=check(owner.post('/api/users',headers=oh,json={
            'username':'synthetic_auditor_viewer','password':'synthetic_viewer_password_2026',
            'role':'viewer'}))['id']
        ch=login(clinician,'synthetic_clinician','synthetic_clinician_password_2026')
        login(viewer,'synthetic_auditor_viewer','synthetic_viewer_password_2026')
        dept=next(x['id'] for x in check(owner.get('/api/lookups'))['departments'] if x['code']=='LAB')

        # The G2Z viewer workaround must not be permitted for new grants.
        check(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'user_id':vid,'department_id':dept,'active':True}),400)
        check(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'user_id':cid,'department_id':dept,'active':True}),409)
        identity={'user_id':cid, 'professional_name':'Synthetic Doctor Testing Only',
                  'registration_reference':'SYN-LICENSE-TEST-ONLY-314159',
                  'review_note':'Verified on synthetic demo evidence only',
                  'current_password':'incorrect_password', 'approved':True}
        check(owner.post('/api/billing/clinical/identity-review',headers=oh,json=identity),403)
        check(owner.post('/api/billing/clinical/identity-review',headers=oh,json={
            **identity,'current_password':'synthetic_clinician_owner_secret_2026'}))
        check(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'user_id':cid,'department_id':dept,'active':True}))
        identities=check(owner.get('/api/billing/clinical/identities'))['items']
        assert any(x['user_id']==cid and x['approved']==1 for x in identities)
        assert all('registration_reference' not in x and 'review_note' not in x for x in identities)
        check(owner.post(f'/api/billing/clinical/departments/{dept}/activate',headers=oh))

        # Medical account must be denied by server even when it guesses URLs.
        assert check(clinician.get('/api/me'))['role']=='clinician'
        for path in ('/api/lookups','/api/reports?month=2026-10','/api/dashboard',
                     '/api/vouchers','/api/export/vouchers.csv', '/api/funds',
                     '/api/billing/patients','/api/billing/cases',
                     '/api/accounting/trial-balance?period=2026-10','/api/users'):
            check(clinician.get(path),403)
        assert check(clinician.get('/api/billing/clinical/queue'))['items']==[]
        # Account credential rotation must invalidate the old professional
        # identity review: newly set passwords may be issued to another human.
        check(owner.post(f'/api/users/{cid}/password',headers=oh,json={
            'password':'synthetic_new_clinician_secret_2026',
            'current_password':'synthetic_clinician_owner_secret_2026'}))
        check(clinician.get('/api/billing/clinical/queue'),401)
        login(clinician,'synthetic_clinician','synthetic_new_clinician_secret_2026')
        check(clinician.get('/api/billing/clinical/queue'),403)
        check(owner.post('/api/billing/clinical/identity-review',headers=oh,json={
            **identity,'current_password':'synthetic_clinician_owner_secret_2026',
            'review_note':'Identity rechecked following synthetic password reset'}))
        assert check(clinician.get('/api/billing/clinical/queue'))['items']==[]
        # Deactivation and later reactivation must also require a new review.
        check(owner.post(f'/api/users/{cid}/status',headers=oh,json={'active':False}))
        check(owner.post(f'/api/users/{cid}/status',headers=oh,json={'active':True}))
        login(clinician,'synthetic_clinician','synthetic_new_clinician_secret_2026')
        check(clinician.get('/api/billing/clinical/queue'),403)
        check(owner.post('/api/billing/clinical/identity-review',headers=oh,json={
            **identity,'current_password':'synthetic_clinician_owner_secret_2026',
            'review_note':'Identity rechecked after synthetic account reactivation'}))
        assert check(clinician.get('/api/billing/clinical/queue'))['items']==[]
        check(viewer.get('/api/billing/clinical/queue'),403)
        check(owner.post('/api/billing/clinical/identity-review',headers=oh,json={
            **identity,'approved':False,'review_note':'Access revoked after synthetic rotation',
            'current_password':'synthetic_clinician_owner_secret_2026'}))
        check(clinician.get('/api/billing/clinical/queue'),403)
        check(owner.post('/api/billing/clinical/grants',headers=oh,json={
            'user_id':cid,'department_id':dept,'active':True}),409)
        with connect() as c:
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert c.execute('SELECT role FROM users WHERE id=?',(cid,)).fetchone()[0]=='clinician'
            assert not any('SYN-LICENSE' in row[0] for row in c.execute(
                "SELECT details FROM audit_log WHERE action='clinical_identity_review'")), 'Medical registration leaked to financial audit log'
        print('PASS G3A clinician account isolated from all financial routes; manual approval and revocation enforced')

if __name__=='__main__':run()
