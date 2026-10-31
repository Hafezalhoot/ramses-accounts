"""G2R TDD: synthetic occupied bed -> priced nights -> ordinary service/invoice path."""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as work:
        os.environ.update(RAMSES_DB_PATH=str(Path(work)/'test.sqlite'), RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='g2r_owner_very_secure_password')
        from bootstrap import initialize, connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner, clerk, reviewer, outsider = [TestClient(app) for _ in range(4)]
        def ok(response, status=200):
            assert response.status_code == status, (response.status_code, response.text, status)
            return response.json() if status == 200 else None
        def signin(client, username, password):
            return {'X-CSRF-Token':ok(client.post('/api/login',json={'username':username,'password':password}))['csrf']}
        oh=signin(owner,'owner','g2r_owner_very_secure_password')
        for username,role in [('g2r_clerk','clerk'),('g2r_reviewer','reviewer'),('g2r_outsider','reviewer')]:
            ok(owner.post('/api/users',headers=oh,json={
                'username':username,'role':role,'password':'g2r_very_secure_employee_password'}))
        ch=signin(clerk,'g2r_clerk','g2r_very_secure_employee_password')
        rh=signin(reviewer,'g2r_reviewer','g2r_very_secure_employee_password')
        xh=signin(outsider,'g2r_outsider','g2r_very_secure_employee_password')
        point=next(p['id'] for p in ok(owner.get('/api/billing/config'))['points'] if p['kind']=='internal')
        for username in ('g2r_clerk','g2r_reviewer'):
            with connect() as c:
                uid=c.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()[0]
            ok(owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={'user_id':uid,'active':True}))
        now=datetime.now(ZoneInfo('Africa/Cairo')).date()
        start=(now-timedelta(days=2)).isoformat()
        next_day=(now-timedelta(days=1)).isoformat()
        today=now.isoformat()
        dept=next(d['id'] for d in ok(owner.get('/api/lookups'))['departments'] if d['code']=='IPD')
        nicu_dept=next(d['id'] for d in ok(owner.get('/api/lookups'))['departments'] if d['code']=='NICU')
        service=ok(owner.post('/api/billing/services',headers=oh,json={
            'code':'G2R_OVERNIGHT','name':'Synthetic single-bed overnight tariff','department_id':dept}))['id']
        ok(owner.post(f'/api/billing/services/{service}/prices',headers=oh,json={'valid_from':start,'amount':'350'}))
        ok(owner.post(f'/api/billing/services/{service}/prices',headers=oh,json={'valid_from':next_day,'amount':'420'}))
        patient=ok(clerk.post('/api/billing/patients',headers=ch,json={
            'display_name':'Synthetic bed case','request_id':'g2r_patient_000000001'}))['id']
        p2=ok(clerk.post('/api/billing/patients',headers=ch,json={
            'display_name':'Synthetic competing patient','request_id':'g2r_patient_000000002'}))['id']
        def open_case(patient_id,index):
            return ok(clerk.post('/api/billing/cases',headers=ch,json={
                'patient_id':patient_id,'point_id':point,'kind':'inpatient',
                'business_date':start,'request_id':f'g2r_case_{index:016d}'}))['id']
        case, other=open_case(patient,1),open_case(p2,2)
        assert reviewer.get('/api/beds/catalog').status_code==403
        bed=ok(owner.post('/api/beds/catalog',headers=oh,json={
            'code':'TEST_BED_G2R_01','name':'Synthetic internal ward bed 01',
            'kind':'inpatient','service_id':service}))['id']
        assert len(ok(owner.get('/api/beds/catalog'))['items'])==1
        assert clerk.post(f'/api/beds/cases/{case}/admit',headers=ch,json={
            'bed_id':bed,'start_date':start,'evidence_reference':'SYN-CLINICAL-ADMISSION-001',
            'request_id':'g2r_clerk_unauthorized_001'}).status_code==403
        stay=ok(owner.post(f'/api/beds/cases/{case}/admit',headers=oh,json={
            'bed_id':bed,'start_date':start,'evidence_reference':'SYN-CLINICAL-ADMISSION-001',
            'request_id':'g2r_admit_stay_00001'}))['id']
        ok(owner.post(f'/api/beds/cases/{case}/admit',headers=oh,json={
            'bed_id':bed,'start_date':start,'evidence_reference':'SYN-CLINICAL-ADMISSION-001',
            'request_id':'g2r_admit_stay_00001'}))
        ok(owner.post(f'/api/beds/cases/{other}/admit',headers=oh,json={
            'bed_id':bed,'start_date':start,'evidence_reference':'SYN-DUPLICATE-ADMISSION-002',
            'request_id':'g2r_occupied_stay_001'}),409)
        assert outsider.get(f'/api/beds/cases/{case}').status_code==403
        assert clerk.get(f'/api/beds/cases/{case}').status_code==200
        report=ok(owner.get(f'/api/beds/cases/{case}?through_date={today}'))
        assert report['unbilled_nights']==2,report
        assert report['preview_total_piasters']==77000,report
        assert [r['amount_piasters'] for r in report['unbilled_preview']]==[35000,42000],report
        clearance=ok(owner.get(f'/api/case-settlement/cases/{case}'))['preflight']
        assert not clearance['ready'] and clearance['open_bed_stays']==1,clearance
        assert owner.post(f'/api/beds/stays/{stay}/charge',headers=oh,json={
            'through_date':(now+timedelta(days=1)).isoformat(),'request_id':'g2r_future_charge_0001'}).status_code==409
        # Direct SQL must not close a case with an active bed even if an approval
        # record is forged; controls need to exist below the API layer.
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rev_id=c.execute("SELECT id FROM users WHERE username='g2r_reviewer'").fetchone()[0]
            c.execute("""INSERT INTO billing_case_clearance_requests
                (case_id,point_id,evidence_reference,note,requested_by,requested_at,
                 status,reviewed_by,reviewed_at,decision_note,closed_on)
                VALUES (?,?,?,?,?,?,'approved',?,?,?,?)""",
                (case,point,'SYN-FORGED-REVIEW-01','SQL-only malicious closure attempt',
                 1,today,rev_id,today,'reviewed elsewhere',today))
            try:c.execute("UPDATE billing_cases SET status='closed' WHERE id=?",(case,))
            except Exception:c.rollback()
            else:
                c.rollback()
                raise AssertionError('SQL-level financial close bypassed active bed stay')
        posted=ok(owner.post(f'/api/beds/stays/{stay}/charge',headers=oh,json={
            'through_date':today,'request_id':'g2r_nights_to_lines_001'}))
        assert posted['created_nights']==2 and posted['total_piasters']==77000,posted
        replay=ok(owner.post(f'/api/beds/stays/{stay}/charge',headers=oh,json={
            'through_date':today,'request_id':'g2r_nights_to_lines_001'}))
        assert replay['replayed'] is True,replay
        assert owner.post(f'/api/beds/stays/{stay}/charge',headers=oh,json={
            'through_date':today,'request_id':'g2r_nights_to_lines_002'}).status_code==409
        first_line=ok(owner.get(f'/api/billing/cases/{case}'))['services'][0]
        assert first_line['is_bed_night'] == 1,first_line
        assert clerk.post(f'/api/billing/lines/{first_line["id"]}/cancel',headers=ch,
            json={'reason':'Direct removal of booked bed night not allowed'}).status_code==409
        with connect() as c:
            charges=c.execute('SELECT * FROM bed_night_charges WHERE stay_id=? ORDER BY night_date',(stay,)).fetchall()
            assert len(charges)==2 and [x['amount_piasters'] for x in charges]==[35000,42000]
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==0
            for stmt in ('UPDATE bed_night_charges SET amount_piasters=1 WHERE id=?',
                         'DELETE FROM bed_night_charges WHERE id=?'):
                try:
                    c.execute(stmt,(charges[0]['id'],))
                except Exception:
                    c.rollback()
                else:
                    raise AssertionError('nightly charge audit row mutated')
        # SQL-level protection: occupancy/charge evidence cannot be attached to
        # another patient's case, even if a future app route makes a mistake.
        other_line=ok(clerk.post(f'/api/billing/cases/{other}/services',headers=ch,json={
            'service_id':service,'quantity':1,'request_id':'g2r_other_line_00001'}))['id']
        with connect() as c:
            for statement,args in [
                ("""INSERT INTO bed_night_charges
                    (stay_id,night_date,case_line_id,price_version_id,amount_piasters,ordered_by,ordered_at)
                    VALUES (?,?,?,?,?,?,?)""",
                 (stay,today,other_line,charges[0]['price_version_id'],35000,1,today)),
                ("""INSERT INTO bed_stays
                    (bed_id,case_id,start_date,admission_evidence,recorded_by,recorded_at)
                    VALUES(?,?,?,?,?,?)""",
                 (bed,other,start,'SYN-FORBIDDEN-COLLISION',1,today))]:
                try:c.execute(statement,args)
                except Exception:c.rollback()
                else:raise AssertionError('SQL-level case/bed integrity check bypassed')
        assert owner.post(f'/api/beds/stays/{stay}/release',headers=oh,json={
            'end_date':start,'evidence_reference':'SYN-INVALID-RELEASE-0001'}).status_code==409
        released=ok(owner.post(f'/api/beds/stays/{stay}/release',headers=oh,json={
            'end_date':today,'evidence_reference':'SYN-RELEASE-000000001'}))
        assert released['end_date']==today,released
        assert owner.post(f'/api/beds/stays/{stay}/release',headers=oh,json={
            'end_date':today,'evidence_reference':'SYN-DUPLICATE-RELEASE'}).status_code==409
        assert not ok(owner.get(f'/api/beds/cases/{case}'))['active_stay']
        for line in ok(owner.get(f'/api/billing/cases/{case}'))['services']:
            ok(reviewer.post(f'/api/billing/lines/{line["id"]}/fulfill',headers=rh))
        pre=ok(owner.get(f'/api/case-settlement/cases/{case}'))['preflight']
        assert pre['open_bed_stays']==0 and pre['uncharged_bed_nights']==0,pre
        assert pre['fulfilled_unbilled']==2,pre
        # Released bed may be reused; each charge remains linked to the original case.
        other_stay=ok(owner.post(f'/api/beds/cases/{other}/admit',headers=oh,json={
            'bed_id':bed,'start_date':today,'evidence_reference':'SYN-CLINICAL-ADMISSION-002',
            'request_id':'g2r_new_stay_0000002'}))['id']
        assert other_stay!=stay
        assert not ok(owner.get(f'/api/beds/cases/{other}'))['unbilled_nights']
        # Same-day administrative occupancy with ZERO nights must be cancellable
        # through the existing independent no-charge clearance, not a fake invoice.
        p3=ok(clerk.post('/api/billing/patients',headers=ch,json={
            'display_name':'Synthetic same-day cancellation','request_id':'g2r_patient_zero_night01'}))['id']
        short_case=open_case(p3,3)
        bed2=ok(owner.post('/api/beds/catalog',headers=oh,json={
            'code':'TEST_BED_G2R_02','name':'Synthetic short visit bed','kind':'inpatient','service_id':service}))['id']
        short_stay=ok(owner.post(f'/api/beds/cases/{short_case}/admit',headers=oh,json={
            'bed_id':bed2,'start_date':today,'evidence_reference':'SYN-SHORT-ADMISSION-001',
            'request_id':'g2r_short_admission_01'}))['id']
        ok(owner.post(f'/api/beds/stays/{short_stay}/release',headers=oh,json={
            'end_date':today,'evidence_reference':'SYN-SHORT-RELEASE-0001'}))
        short_ready=ok(owner.get(f'/api/case-settlement/cases/{short_case}'))['preflight']
        assert short_ready['no_charge_ready'],short_ready
        with connect() as c:
            journals=c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
            receipts=c.execute('SELECT COUNT(*) FROM billing_collections').fetchone()[0]
        req=ok(owner.post(f'/api/case-settlement/cases/{short_case}/request',headers=oh,json={
            'request_id':'g2r_short_zero_charge_01','mode':'no_charge',
            'evidence_reference':'SYN-CASE-CANCEL-0001',
            'note':'Zero overnight occupancy and no patient financial charges'}))['id']
        ok(reviewer.post(f'/api/case-settlement/requests/{req}/decision',headers=rh,json={
            'decision':'approve','note':'Independent review confirms no clinical service or billed night'}))
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==journals
            assert c.execute('SELECT COUNT(*) FROM billing_collections').fetchone()[0]==receipts
        # NICU has its own department and cannot be assigned an IPD bed.
        nursery=ok(owner.post('/api/billing/services',headers=oh,json={
            'code':'G2R_NICU_NIGHT','name':'Synthetic neonatal stay night','department_id':nicu_dept}))['id']
        ok(owner.post(f'/api/billing/services/{nursery}/prices',headers=oh,json={
            'valid_from':start,'amount':'600'}))
        nicu_bed=ok(owner.post('/api/beds/catalog',headers=oh,json={
            'code':'TEST_NICU_BED_G2R','name':'Synthetic NICU bed','kind':'nicu','service_id':nursery}))['id']
        pn=ok(clerk.post('/api/billing/patients',headers=ch,json={
            'display_name':'Synthetic NICU patient','request_id':'g2r_nicu_patient_0001'}))['id']
        nicu_case=ok(clerk.post('/api/billing/cases',headers=ch,json={
            'patient_id':pn,'point_id':point,'kind':'nicu','business_date':today,
            'request_id':'g2r_nicu_case_000001'}))['id']
        ok(owner.post(f'/api/beds/cases/{nicu_case}/admit',headers=oh,json={
            'bed_id':bed2,'start_date':today,'evidence_reference':'SYN-NICU-WRONG-BED-01',
            'request_id':'g2r_nicu_wrong_bed_01'}),409)
        ok(owner.post(f'/api/beds/cases/{nicu_case}/admit',headers=oh,json={
            'bed_id':nicu_bed,'start_date':today,'evidence_reference':'SYN-NICU-ADMISSION-0001',
            'request_id':'g2r_nicu_stay_0000001'}))
        assert ok(owner.get(f'/api/beds/cases/{nicu_case}'))['active_stay']['bed_id']==nicu_bed
        print('PASS G2R: occupancy, period-specific night fees, atomic charges, scope, immutable audit, close gate')

if __name__=='__main__':run()
