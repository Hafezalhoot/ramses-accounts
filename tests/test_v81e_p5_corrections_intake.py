"""Actual correction intake: independent triage and immutable source, zero financial impact."""
import os,sys,tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def run():
 with tempfile.TemporaryDirectory() as tmp:
    os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'corrections.sqlite3')
    os.environ['RAMSES_ADMIN_USER']='owner';os.environ['RAMSES_ADMIN_PASSWORD']='owner_correct_secure_2026'
    from bootstrap import initialize,connect
    initialize()
    from app import app
    from fastapi.testclient import TestClient
    owner, clerk, reviewer, outsider=(TestClient(app) for _ in range(4))
    def login(c,user,pw):
        r=c.post('/api/login',json={'username':user,'password':pw});assert r.status_code==200,r.text
        return {'X-CSRF-Token':r.json()['csrf']}
    oh=login(owner,'owner','owner_correct_secure_2026')
    for name,role in [('clerk_a','clerk'),('clerk_b','clerk'),('reviewer_a','reviewer')]:
        assert owner.post('/api/users',headers=oh,json={'username':name,'password':'clerk_correct_password_2026','role':role}).status_code==200
    ch=login(clerk,'clerk_a','clerk_correct_password_2026')
    vh=login(reviewer,'reviewer_a','clerk_correct_password_2026')
    xh=login(outsider,'clerk_b','clerk_correct_password_2026')
    user_id=next(x['id'] for x in owner.get('/api/users').json() if x['username']=='clerk_a')
    pts=owner.get('/api/billing/config').json()['points'];ext=next(x['id'] for x in pts if x['kind']=='external')
    assert owner.post(f'/api/billing/points/{ext}/assign',headers=oh,json={'user_id':user_id}).status_code==200
    fund=owner.post('/api/funds',headers=oh,json={'code':'fix_till','name':'خزنة تصحيح تجريبية','kind':'cash'}).json()['id']
    assert owner.post(f'/api/billing/points/{ext}/cash-fund',headers=oh,json={'fund_id':fund}).status_code==200
    day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    shift=clerk.post('/api/shifts/open',headers=ch,json={'business_date':day,'shift':'night','fund_id':fund})
    assert shift.status_code==200,shift.text
    patient=clerk.post('/api/billing/patients',headers=ch,json={'display_name':'A test patient for corrections','request_id':'correction_patient_1001'})
    assert patient.status_code==200,patient.text
    case=clerk.post('/api/billing/cases',headers=ch,json={'patient_id':patient.json()['id'],'kind':'outpatient',
                 'point_id':ext,'business_date':day,'request_id':'correction_case_1001'})
    assert case.status_code==200,case.text
    dept=next(x['id'] for x in owner.get('/api/lookups').json()['departments'] if x['code']=='LAB')
    service=owner.post('/api/billing/services',headers=oh,json={'code':'CORRECTION_A100','name':'Correction mock lab service','department_id':dept})
    assert service.status_code==200,service.text
    assert owner.post(f'/api/billing/services/{service.json()["id"]}/prices',headers=oh,json={'valid_from':day,'amount':'500'}).status_code==200
    line=clerk.post(f'/api/billing/cases/{case.json()["id"]}/services',headers=ch,json={'service_id':service.json()['id'],
       'quantity':1,'request_id':'correction_line_1001'})
    assert line.status_code==200,line.text
    from reviewer_scope_helpers import grant_reviewers_for_test
    grant_reviewers_for_test(owner, oh)
    assert reviewer.post(f'/api/billing/lines/{line.json()["id"]}/fulfill',headers=vh).status_code==200
    draft=clerk.post(f'/api/billing/cases/{case.json()["id"]}/drafts',headers=ch,json={'request_id':'correction_draft_1001'})
    assert draft.status_code==200,draft.text
    invoice=clerk.post(f'/api/billing/drafts/{draft.json()["id"]}/issue',headers=ch,json={'request_id':'correction_issue_1001'})
    assert invoice.status_code==200,invoice.text
    with connect() as c:
        journals=c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
        movements=c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
    payload={'source_type':'invoice','source_id':invoice.json()['id'],'issue_type':'wrong_patient',
       'reason':'اسم المريض على الفاتورة غير مطابق للمستند الطبي ونحتاج تحقيقًا موثقًا',
       'proposed_resolution':'التحقق من المستندات ثم اعتماد التصحيح المستقل',
       'request_key':'unique_correction_100001'}
    assert outsider.post('/api/corrections',headers=xh,json=payload).status_code==403
    opened=clerk.post('/api/corrections',headers=ch,json=payload)
    assert opened.status_code==200,opened.text;id=opened.json()['id']
    assert clerk.post('/api/corrections',headers=ch,json=payload).json()['replayed']
    assert clerk.post('/api/corrections',headers=ch,json={**payload,'source_id':9999}).status_code==409
    assert outsider.get(f'/api/corrections/{id}/history').status_code==403
    assert outsider.get('/api/corrections').json()['tickets']==[]
    assert clerk.post(f'/api/corrections/{id}/review',headers=ch,json={'decision':'triage','note':'محاولة اعتماد ذاتية ممنوعة'}).status_code==403
    evidence=reviewer.post(f'/api/corrections/{id}/review',headers=vh,json={'decision':'needs_evidence','note':'مطلوب صورة المستند الأصلي للمراجعة'})
    assert evidence.status_code==200 and not evidence.json()['financial_posted'],evidence.text
    append=clerk.post(f'/api/corrections/{id}/note',headers=ch,json={'note':'تم الحصول على صورة المستند وحفظ مرجعه بالمستشفى'})
    assert append.status_code==200,append.text
    triage=reviewer.post(f'/api/corrections/{id}/review',headers=vh,json={'decision':'triage','note':'قبول البلاغ للفحص فقط دون تعديل الفاتورة'})
    assert triage.status_code==200 and triage.json()['status']=='triaged',triage.text
    assert reviewer.post(f'/api/corrections/{id}/review',headers=vh,json={'decision':'triage','note':'طلب مكرر غير مطلوب'}).status_code==409
    history=clerk.get(f'/api/corrections/{id}/history').json()
    assert [e['action'] for e in history['events']]==['opened','needs_evidence','note','triaged']
    with connect() as c:
        assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==journals
        assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==movements
        assert c.execute('SELECT total_piasters,status FROM billing_invoices WHERE id=?',(invoice.json()['id'],)).fetchone()['total_piasters']==50000
        row=c.execute('SELECT source_snapshot_json FROM financial_correction_tickets WHERE id=?',(id,)).fetchone()
        assert '50000' in row[0]
        try:c.execute('DELETE FROM financial_correction_events WHERE ticket_id=?',(id,))
        except Exception:pass
        else:raise AssertionError('Correction event deleted')
        try:c.execute('UPDATE financial_correction_tickets SET source_id=0 WHERE id=?',(id,))
        except Exception:pass
        else:raise AssertionError('Correction origin modified')
    print('PASS P5 correction tickets: source scoping, idempotency, independent review, append-only events, ZERO ledger impact')
if __name__=='__main__':run()
