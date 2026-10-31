"""G2B: old visit -> current invoice, never fabricated historical cash."""
import os
import sys
import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
 with tempfile.TemporaryDirectory() as path:
    os.environ['RAMSES_DB_PATH']=str(Path(path)/'g2b.sqlite3')
    os.environ['RAMSES_ADMIN_USER']='owner'
    os.environ['RAMSES_ADMIN_PASSWORD']='owner_g2b_secure_password'
    from bootstrap import connect,initialize
    initialize()
    from fastapi.testclient import TestClient
    from app import app
    import billing
    clients=[TestClient(app) for _ in range(3)]
    def login(client,user,password):
        r=client.post('/api/login',json={'username':user,'password':password})
        assert r.status_code==200,r.text
        return {'X-CSRF-Token':r.json()['csrf']}
    owner,reviewer,outsider=clients
    oh=login(owner,'owner','owner_g2b_secure_password')
    for name,role in [('review_g2b','reviewer'),('outsider_g2b','clerk')]:
        r=owner.post('/api/users',headers=oh,json={'username':name,'password':'g2b_staff_secure_password','role':role})
        assert r.status_code==200,r.text
    rh=login(reviewer,'review_g2b','g2b_staff_secure_password')
    xh=login(outsider,'outsider_g2b','g2b_staff_secure_password')
    ext=next(x for x in owner.get('/api/billing/config').json()['points'] if x['kind']=='external')
    point=ext['id']
    today=datetime.now(ZoneInfo('Africa/Cairo')).date()
    old=today.replace(day=1)-timedelta(days=1)
    old_day=old.isoformat()
    with connect() as c:
        c.execute('UPDATE cashier_schedule_versions SET starts_on=? WHERE point_id=?',(old_day,point))
        c.execute('UPDATE cashier_point_lifecycle SET starts_on=? WHERE point_id=?',(old_day,point))
        uid=c.execute("SELECT id FROM users WHERE username='owner'").fetchone()[0]
        c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES (?,?,?)',
                  (old_day[:7],uid,datetime.now(ZoneInfo('UTC')).isoformat()))
    p=owner.post('/api/billing/patients',headers=oh,json={'display_name':'مريض اختبار تاريخي افتراضي','request_id':'g2b_patient_2026_0001'})
    assert p.status_code==200,p.text
    patient=p.json()['id']
    patient_code=p.json()['code']
    assert owner.post('/api/billing/cases',headers=oh,json={
      'patient_id':patient,'kind':'outpatient','point_id':point,'business_date':old_day,
      'request_id':'g2b_standard_case_001'}).status_code==409
    incident={'request_key':'g2b_incident_2026_0001','point_id':point,'business_date':old_day,
       'shift_code':'night','incident_reason':'absence','custodian_name':'موظف حفظ النقدية الوهمية',
       'cash_location':'envelope','counted_cash':'900','source_register_ref':'G2B-TEST-ENV',
       'note':'إيصالات حدثت في فترة قديمة مقفولة ولم تدخل إلى النظام الإلكتروني'}
    ii=owner.post('/api/late-entries',headers=oh,json=incident)
    assert ii.status_code==200,ii.text
    inc=ii.json()['id']
    dd=owner.post(f'/api/late-entries/{inc}/documents',headers=oh,json={
       'paper_ref':'G2B-PAPER-001','kind':'patient_receipt','amount':'900','method':'cash'})
    assert dd.status_code==200,dd.text
    doc=dd.json()['id']
    payload={'request_id':'g2b_recover_case_key_0001','patient_code':patient_code,
             'kind':'outpatient','note':'إدخال حالة قديمة بمستند أصلي وتحقق مستقل من تنفيذ الخدمة'}
    assert owner.post(f'/api/late-entries/{inc}/documents/{doc}/recover-case',headers=oh,json=payload).status_code==409
    assert owner.post(f'/api/late-entries/{inc}/action',headers=oh,json={'action':'submit','note':'الواقعة جاهزة للمراجعة المالية'}).status_code==200
    from reviewer_scope_helpers import grant_reviewers_for_test
    grant_reviewers_for_test(owner, oh)
    assert reviewer.post(f'/api/late-entries/{inc}/action',headers=rh,json={'action':'triage','note':'تم التحقق من أصل الورقة وبيانات الحيازة'}).status_code==200
    assert outsider.post(f'/api/late-entries/{inc}/documents/{doc}/recover-case',headers=xh,json=payload).status_code==403
    new=owner.post(f'/api/late-entries/{inc}/documents/{doc}/recover-case',headers=oh,json=payload)
    assert new.status_code==200,new.text
    case=new.json()['id']
    assert new.json()['financial_posted'] is False and new.json()['cash_posted'] is False
    assert owner.post(f'/api/late-entries/{inc}/documents/{doc}/recover-case',headers=oh,json=payload).json()['replayed']
    assert owner.post(f'/api/late-entries/{inc}/documents/{doc}/recover-case',headers=oh,
      json={**payload,'request_id':'g2b_new_duplicate_case_01'}).status_code==409
    with connect() as c:
        assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==0
        assert c.execute('SELECT business_date FROM billing_cases WHERE id=?',(case,)).fetchone()[0]==old_day
    dept=owner.get('/api/lookups').json()['departments'][0]['id']
    srv=owner.post('/api/billing/services',headers=oh,json={'code':'G2B_SERVICE_01','name':'خدمة تاريخية تجريبية فقط',
       'department_id':dept,'suggested_point':'either'})
    assert srv.status_code==200,srv.text
    service=srv.json()['id']
    assert owner.post(f'/api/billing/services/{service}/prices',headers=oh,json={'valid_from':old_day,'amount':'900'}).status_code==200
    assert owner.post(f'/api/billing/services/{service}/prices',headers=oh,json={'valid_from':today.isoformat(),'amount':'1500'}).status_code==200
    line=owner.post(f'/api/billing/cases/{case}/services',headers=oh,json={
       'service_id':service,'quantity':1,'request_id':'g2b_old_line_2026_01'})
    assert line.status_code==200,line.text
    assert line.json()['unit_price_piasters']==90000
    assert reviewer.post(f'/api/billing/lines/{line.json()["id"]}/fulfill',headers=rh).status_code==200
    draft=owner.post(f'/api/billing/cases/{case}/drafts',headers=oh,json={'request_id':'g2b_old_draft_2026_01'})
    assert draft.status_code==200,draft.text
    # Reviewer can request fresh proof after a draft is already prepared.
    # That must block posting until an independent reviewer clears it again.
    assert reviewer.post(f'/api/late-entries/{inc}/action',headers=rh,
      json={'action':'needs_evidence','note':'وردتنا معلومة جديدة تتطلب مستندًا إضافيًا'}).status_code==200
    on_hold=owner.post(f'/api/billing/drafts/{draft.json()["id"]}/issue',headers=oh,
      json={'request_id':'g2b_old_invoice_on_hold_01'})
    assert on_hold.status_code==409,on_hold.text
    with connect() as c:
        assert c.execute('SELECT count(*) FROM gl_journals').fetchone()[0]==0
    assert owner.post(f'/api/late-entries/{inc}/action',headers=oh,
      json={'action':'submit','note':'استكملنا التحقق من الخدمة القديمة وأصل المستند'}).status_code==200
    assert reviewer.post(f'/api/late-entries/{inc}/action',headers=rh,
      json={'action':'triage','note':'أعدت مراجعة الملف والمستند واستوفى الشروط'}).status_code==200
    inv=owner.post(f'/api/billing/drafts/{draft.json()["id"]}/issue',headers=oh,
      json={'request_id':'g2b_old_invoice_2026_01'})
    assert inv.status_code==200,inv.text
    with connect() as c:
        invrow=c.execute('SELECT i.issued_date,j.entry_date,i.total_piasters FROM billing_invoices i '
          'JOIN gl_journals j ON j.id=i.journal_id WHERE i.id=?',(inv.json()['id'],)).fetchone()
        assert (invrow['issued_date'],invrow['entry_date'],invrow['total_piasters'])==(today.isoformat(),today.isoformat(),90000)
        assert c.execute('SELECT count(*) FROM fund_movements').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM billing_collections').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM gl_journals').fetchone()[0]==1
        assert 'فاتورة استدراك' in c.execute('SELECT memo FROM gl_journals WHERE id=(SELECT journal_id FROM billing_invoices WHERE id=?)',(inv.json()['id'],)).fetchone()[0]
        assert c.execute('SELECT count(*) FROM periods WHERE period=?',(old_day[:7],)).fetchone()[0]==1
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        # No alterations or deletes to the origin of the late event.
        try:
            c.execute('DELETE FROM billing_late_cases WHERE case_id=?',(case,))
        except Exception:
            pass
        else:
            raise AssertionError('Late case origin unexpectedly deletable')
    summary=owner.get('/api/billing/summary',params={'period':today.strftime('%Y-%m')})
    assert summary.status_code==200,summary.text
    assert summary.json()['late_service_revenue_this_month_piasters']==90000
    assert summary.json()['late_service_invoices_this_month']==1
    assert summary.json()['collections_this_month_piasters']==0
    finance=owner.get(f'/api/billing/cases/{case}/finance')
    assert finance.status_code==200 and finance.json()['cash_collection_blocked']
    assert finance.json()['late_recovery']['incident_id']==inc
    cash_sub=next(x['id'] for x in owner.get('/api/funds').json() if x['code']=='cash_sub')
    assert owner.post(f'/api/billing/points/{point}/cash-fund',headers=oh,json={'fund_id':cash_sub}).status_code==200
    opened=owner.post('/api/shifts/open',headers=oh,json={
       'fund_id':cash_sub,'business_date':today.isoformat(),'shift':'night'})
    assert opened.status_code==200,opened.text
    denied=owner.post(f'/api/billing/cases/{case}/collect',headers=oh,json={
       'point_id':point,'invoice_id':inv.json()['id'],
       'parts':[{'method':'cash','amount':'900'}],
       'request_id':'g2b_do_not_duplicate_cash_0001'})
    assert denied.status_code==409 and 'تاريخية' in denied.text,denied.text
    with connect() as c:
        assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==0
        # Isolate month-end rule: other scheduled shifts from the current month
        # are disabled in this TEMPORARY database so they do not mask the
        # late-invoice-specific barrier.
        for row in c.execute('SELECT id FROM billing_points').fetchall():
            c.execute('INSERT OR REPLACE INTO cashier_point_lifecycle(point_id,starts_on,enabled) VALUES (?,?,0)',
                      (row['id'],today.strftime('%Y-%m-01')))
        # A test shift is open. Close only its status directly in the sandbox
        # to check the independent G2B control; production would use the full
        # cash count, handover, and independent review.
        c.execute("UPDATE shift_sessions SET status='closed' WHERE fund_id=?",(cash_sub,))
    blocked=owner.get('/api/periods/preflight',params={'period':today.strftime('%Y-%m')})
    assert blocked.status_code==200 and not blocked.json()['ready'],blocked.text
    assert 'فاتورة مستدركة' in blocked.json()['reason'],blocked.text
    with connect() as c:
        assert c.execute('SELECT COUNT(*) FROM billing_collections').fetchone()[0]==0
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    d=owner.get(f'/api/late-entries/{inc}').json()
    assert d['recovered_cases'][0]['case_id']==case
    assert d['recovered_cases'][0]['issued_invoice_no']==inv.json()['invoice_no']
    print('PASS G2B: closed-old-month late visit; independent triage; historical pricing; current GL; no invented cash')

if __name__=='__main__':run()
