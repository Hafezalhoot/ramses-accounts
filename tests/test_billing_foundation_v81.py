"""V8.1A end-to-end finances: station privacy, case route, price snapshots, draft idempotency."""
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'billing.db')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='test_only_owner_pass_2026'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        from bootstrap import initialize, connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        owner=TestClient(app)
        clerk=TestClient(app)
        reviewer=TestClient(app)
        stranger=TestClient(app)
        def signin(client,name,pw):
            res=client.post('/api/login',json={'username':name,'password':pw})
            assert res.status_code==200,res.text
            return {'X-CSRF-Token':res.json()['csrf']}
        oh=signin(owner,'owner','test_only_owner_pass_2026')
        def newstaff(name,role):
            res=owner.post('/api/users',json={'username':name,'password':'test_staff_secure_pass_2026','role':role},headers=oh)
            assert res.status_code==200,res.text
            return res.json()['id']
        clerkid=newstaff('cashier', 'clerk')
        rid=newstaff('accountant','reviewer')
        newstaff('other_cashier','clerk')
        ch=signin(clerk,'cashier','test_staff_secure_pass_2026')
        rh=signin(reviewer,'accountant','test_staff_secure_pass_2026')
        sh=signin(stranger,'other_cashier','test_staff_secure_pass_2026')
        no=TestClient(app)
        assert no.get('/api/billing/config').status_code==401
        points=owner.get('/api/billing/config').json()['points']
        assert {p['kind'] for p in points}=={'external','internal'}
        external=next(p['id'] for p in points if p['kind']=='external')
        internal=next(p['id'] for p in points if p['kind']=='internal')
        assert clerk.get('/api/billing/config').json()['points']==[]
        r=owner.post(f'/api/billing/points/{external}/assign',json={'user_id':clerkid,'active':True},headers=oh)
        assert r.status_code==200,r.text
        assert [p['id'] for p in clerk.get('/api/billing/config').json()['points']]==[external]
        assert stranger.get('/api/billing/cases').json()['items']==[]
        # A cashier cannot assign itself nor open a financial case for another station.
        assert clerk.post(f'/api/billing/points/{internal}/assign',json={'user_id':clerkid},headers=ch).status_code==403
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        depts=owner.get('/api/lookups').json()['departments']
        lab=next(x['id'] for x in depts if x['code']=='LAB')
        s=owner.post('/api/billing/services',json={'code':'T_LAB_PANEL','name':'تحاليل مختبر وهمية','department_id':lab,'suggested_point':'external'},headers=oh)
        assert s.status_code==200,s.text
        service_id=s.json()['id']
        assert clerk.post('/api/billing/services',headers=ch,json={'code':'T_FORBIDDEN','name':'خدمة ممنوعة','department_id':lab,'suggested_point':'either'}).status_code==403
        p=owner.post(f'/api/billing/services/{service_id}/prices',headers=oh,json={'valid_from':day,'amount':'450.25'})
        assert p.status_code==200,p.text
        assert owner.post(f'/api/billing/services/{service_id}/prices',headers=oh,json={'valid_from':day,'amount':'9'}).status_code==409
        patient=clerk.post('/api/billing/patients',headers=ch,json={'display_name':'مريض اختبار لا بيانات حقيقية','request_id':'patient_case_key_123456'})
        assert patient.status_code==200,patient.text
        pid=patient.json()['id']
        again=clerk.post('/api/billing/patients',headers=ch,json={'display_name':'مريض اختبار لا بيانات حقيقية','request_id':'patient_case_key_123456'})
        assert again.status_code==200 and again.json()['id']==pid and again.json()['replayed']
        assert clerk.get('/api/billing/patients?q=مريض').json()['items']==[]
        # Enumerating another patient's numeric ID must not grant a clerk access.
        other=owner.post('/api/billing/patients',headers=oh,json={
            'display_name':'مريض وهمي آخر','request_id':'owner_patient_id_12345678'})
        assert other.status_code==200,other.text
        otherid=other.json()['id']
        assert clerk.post('/api/billing/cases',headers=ch,json={
            'patient_id':otherid,'kind':'outpatient','point_id':external,'business_date':day,
            'request_id':'guess_patient_case_12345'}).status_code==403
        assert clerk.get('/api/billing/patients?q='+patient.json()['code']).json()['items'][0]['id']==pid
        # Outpatient case is held by the cashier's assigned station.
        case_payload={'patient_id':pid,'kind':'outpatient','point_id':external,'business_date':day,'request_id':'case_test_1234567890'}
        case=clerk.post('/api/billing/cases',headers=ch,json=case_payload)
        assert case.status_code==200,case.text
        case_id=case.json()['id']
        assert clerk.post('/api/billing/cases',headers=ch,json=case_payload).json()['id']==case_id
        assert clerk.post('/api/billing/cases',headers=ch,json={**case_payload,'kind':'inpatient','request_id':'case_test_0987654321'}).status_code==403
        assert clerk.post('/api/billing/cases',headers=ch,json={**case_payload,'point_id':internal,'request_id':'case_test_2345678901'}).status_code==403
        assert stranger.get(f'/api/billing/cases/{case_id}').status_code==403
        from reviewer_scope_helpers import grant_reviewers_for_test
        grant_reviewers_for_test(owner, oh)
        assert reviewer.get('/api/billing/cases').status_code==200
        # Lab service may be ordered in an internal patient case: location != payer point.
        internal_case=owner.post('/api/billing/cases',headers=oh,json={
          'patient_id':pid,'kind':'inpatient','point_id':internal,'business_date':day,
          'request_id':'internal_case_123456789'})
        assert internal_case.status_code==200,internal_case.text
        inpatient=internal_case.json()['id']
        assert clerk.get(f'/api/billing/cases/{inpatient}').status_code==403
        assert clerk.post(f'/api/billing/cases/{inpatient}/services',headers=ch,json={
          'service_id':service_id,'quantity':1,'request_id':'clerk_cannot_123456789'}).status_code==403
        l=owner.post(f'/api/billing/cases/{inpatient}/services',headers=oh,json={
          'service_id':service_id,'quantity':2,'request_id':'order_internal_1234567890'})
        assert l.status_code==200,l.text
        line=l.json()['id'];assert l.json()['unit_price_piasters']==45025
        assert owner.post(f'/api/billing/cases/{inpatient}/services',headers=oh,json={
          'service_id':service_id,'quantity':2,'request_id':'order_internal_1234567890'}).json()['id']==line
        assert owner.post(f'/api/billing/cases/{inpatient}/drafts',headers=oh,json={'request_id':'draft_before_fulfilled_123'}).status_code==409
        from datetime import timedelta
        tomorrow=(date.fromisoformat(day)+timedelta(days=1)).isoformat()
        newer=owner.post(f'/api/billing/services/{service_id}/prices',headers=oh,json={
            'valid_from':tomorrow,'amount':'600'})
        assert newer.status_code==200,newer.text
        # An already registered service keeps its own price snapshot forever.
        before=owner.get(f'/api/billing/cases/{inpatient}').json()['services'][0]
        assert before['unit_price_piasters']==45025
        assert owner.post(f'/api/billing/lines/{line}/fulfill',headers=oh).status_code==200
        assert owner.post(f'/api/billing/lines/{line}/fulfill',headers=oh).status_code==409
        assert owner.post(f'/api/billing/lines/{line}/cancel',headers=oh,json={'reason':'مسموح فقط قبل تنفيذ الخدمة'}).status_code==409
        d=owner.post(f'/api/billing/cases/{inpatient}/drafts',headers=oh,json={'request_id':'invoice_draft_key_123456'})
        assert d.status_code==200,d.text
        assert d.json()['total_piasters']==90050 and d.json()['status']=='draft'
        assert not d.json()['accounting_posted']
        draft_id=d.json()['id']
        assert owner.post(f'/api/billing/cases/{inpatient}/drafts',headers=oh,json={'request_id':'invoice_draft_key_123456'}).json()['id']==draft_id
        assert owner.post(f'/api/billing/cases/{inpatient}/drafts',headers=oh,json={'request_id':'invoice_draft_other_123456'}).status_code==409
        assert clerk.get(f'/api/billing/drafts/{draft_id}').status_code==403
        details=reviewer.get(f'/api/billing/drafts/{draft_id}').json()
        assert details['draft']['total_piasters']==90050 and 'مسودة' in details['watermark']
        assert details['lines'][0]['service_name_snapshot']=='تحاليل مختبر وهمية'
        assert owner.get(f'/api/billing/cases/{inpatient}').json()['unbilled_piasters']==0
        month=day[:7]
        assert owner.post('/api/periods/close',headers=oh,json={'period':month}).status_code==409
        # Critical: a DRAFT must not book earned revenue, cash or patient receivable.
        with connect() as c:
            assert c.execute('SELECT count(*) FROM gl_journals').fetchone()[0]==0
            assert c.execute('SELECT count(*) FROM fund_movements').fetchone()[0]==0
            assert c.execute('SELECT count(*) FROM billing_invoice_drafts').fetchone()[0]==1
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        # Existing database compatible with second initialization.
        initialize()
        with connect() as c:
            assert c.execute('SELECT count(*) FROM billing_invoice_drafts').fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM billing_points').fetchone()[0]==2
        print('PASS V8.1A: dual-station permissions, separate internal case, catalog prices, fulfillment, idempotency, unposted draft')


if __name__=='__main__':run()
