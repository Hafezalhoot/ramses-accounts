"""Posted patient invoices must not permanently prohibit month closure.

Isolate billing gate by marking both test cashier points inactive in the
TEMPORARY database after invoice issuance. No hospital database is modified.
"""
from unittest.mock import patch
import os,sys,tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def run():
 with tempfile.TemporaryDirectory() as tmp:
    os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'billing_gate.sqlite3')
    os.environ['RAMSES_ADMIN_USER']='owner'
    os.environ['RAMSES_ADMIN_PASSWORD']='owner_billing_gate_test_password'
    from bootstrap import initialize,connect
    initialize()
    from app import app
    from fastapi.testclient import TestClient
    owner=TestClient(app);review=TestClient(app)
    def signin(c,user,pw):
        r=c.post('/api/login',json={'username':user,'password':pw});assert r.status_code==200,r.text
        return {'X-CSRF-Token':r.json()['csrf']}
    oh=signin(owner,'owner','owner_billing_gate_test_password')
    assert owner.post('/api/users',headers=oh,json={'username':'nurse_reviewer','password':'staff_billing_gate_password','role':'reviewer'}).status_code==200
    rh=signin(review,'nurse_reviewer','staff_billing_gate_password')
    day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    month=day[:7]
    point=next(x for x in owner.get('/api/billing/config').json()['points'] if x['kind']=='external')['id']
    dept=owner.get('/api/lookups').json()['departments'][0]['id']
    patient=owner.post('/api/billing/patients',headers=oh,json={'display_name':'مريض افتراضي لاختبار الإقفال','request_id':'g0_patient_gate_2026'});
    assert patient.status_code==200,patient.text
    case=owner.post('/api/billing/cases',headers=oh,json={'patient_id':patient.json()['id'],
       'kind':'outpatient','point_id':point,'business_date':day,'request_id':'g0_case_gate_2026'})
    assert case.status_code==200,case.text
    case_id=case.json()['id']
    s=owner.post('/api/billing/services',headers=oh,json={'code':'G0_TEST_SERVICE','name':'خدمة علاجية افتراضية للاختبار',
       'department_id':dept,'suggested_point':'either'});assert s.status_code==200,s.text
    assert owner.post(f'/api/billing/services/{s.json()["id"]}/prices',headers=oh,json={'valid_from':day,'amount':'1500'}).status_code==200
    line=owner.post(f'/api/billing/cases/{case_id}/services',headers=oh,json={'service_id':s.json()['id'],
       'quantity':1,'request_id':'g0_service_gate_2026'});assert line.status_code==200,line.text
    from reviewer_scope_helpers import grant_reviewers_for_test
    grant_reviewers_for_test(owner, oh)
    assert review.post(f'/api/billing/lines/{line.json()["id"]}/fulfill',headers=rh).status_code==200
    draft=owner.post(f'/api/billing/cases/{case_id}/drafts',headers=oh,json={'request_id':'g0_draft_gate_2026'});
    assert draft.status_code==200,draft.text
    # All configured points are closed FOR THIS ISOLATED TEST ONLY, to validate
    # the billing gate rather than expected shift gate.
    with connect() as c:
        c.execute('UPDATE cashier_point_lifecycle SET enabled=0')
    pending=owner.post('/api/periods/close',headers=oh,json={'period':month})
    assert pending.status_code==409 and 'مسودات' in pending.text,pending.text
    # Reactivate ONLY the external station to issue the pending document.
    with connect() as c:
        c.execute('UPDATE cashier_point_lifecycle SET enabled=1 WHERE point_id=?',(point,))
    issued=owner.post(f'/api/billing/drafts/{draft.json()["id"]}/issue',headers=oh,
                     json={'request_id':'g0_issue_gate_2026'})
    assert issued.status_code==200,issued.text
    with connect() as c:
        c.execute('UPDATE cashier_point_lifecycle SET enabled=0')
    data=owner.get('/api/reports',params={'month':month}).json()
    assert data['recognized_revenue_piasters']==150000,data
    assert data['recognized_cash_service_revenue_piasters']==0,data
    # Test clock only: emulate period already completed; production rejects current/future closes.
    with patch('app.current_month', return_value='9999-12'):
        preflight=owner.get('/api/periods/preflight',params={'period':month})
        assert preflight.status_code==200 and preflight.json()['ready'],preflight.text
        ok=owner.post('/api/periods/close',headers=oh,json={'period':month})
        assert ok.status_code==200,ok.text
    assert owner.post('/api/periods/close',headers=oh,json={'period':month}).status_code==409
    print('PASS G0-05: unissued draft blocks close, issued invoice recognized in GL, posted case no longer blocks close')

if __name__=='__main__':run()
