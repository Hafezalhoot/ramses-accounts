"""Isolated G1/G2A gates: restricted cash, paper exceptions, independent matching."""
import io
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as temp:
        os.environ['RAMSES_DB_PATH']=str(Path(temp)/'g1_g2a.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='safe_owner_password_2026'
        from bootstrap import initialize,connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        owner,staff,reviewer,outsider=(TestClient(app) for _ in range(4))
        def login(c,n,p):
            a=c.post('/api/login',json={'username':n,'password':p})
            assert a.status_code==200,a.text
            return {'X-CSRF-Token':a.json()['csrf']}
        oh=login(owner,'owner','safe_owner_password_2026')
        for name,role in [('worker_g2','clerk'),('accountant_g2','reviewer'),('stranger_g2','clerk')]:
            r=owner.post('/api/users',headers=oh,json={'username':name,'password':'safe_worker_password_2026','role':role})
            assert r.status_code==200,r.text
        sh=login(staff,'worker_g2','safe_worker_password_2026')
        rh=login(reviewer,'accountant_g2','safe_worker_password_2026')
        xh=login(outsider,'stranger_g2','safe_worker_password_2026')
        ids={r['username']:r['id'] for r in owner.get('/api/users').json()}
        look=owner.get('/api/lookups').json()
        dept=next(d['id'] for d in look['departments'] if d['code']=='ADMIN')
        cat=next(x['id'] for x in look['categories'] if x['code']=='other_revenue')
        today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        # G1: explicit cash grant on restricted fund; submission/approval separate.
        raw=owner.post('/api/funds',headers=oh,json={
            'code':'restricted_g2','name':'خزنة اختبار صلاحيات جديدة','kind':'cash','restricted_cash':True})
        assert raw.status_code==200,raw.text
        fid=raw.json()['id']
        body={'date':today,'kind':'receipt','shift':'central','from_fund_id':fid,
              'department_id':dept,'category_id':cat,'amount':'75','description':'سند عزل صلاحيات الخزنة'}
        assert staff.post('/api/vouchers',headers=sh,json=body).status_code==403
        blocked_shift=staff.post('/api/shifts/open',headers=sh,json={
          'business_date':today,'shift':'night','fund_id':fid})
        assert blocked_shift.status_code==403,blocked_shift.text
        assert owner.post('/api/fund-access',headers=oh,json={
          'user_id':ids['worker_g2'],'fund_id':fid,'can_submit':True,
          'reason':'تفويض مؤقت لسند اختبار نقدي'}).status_code==200
        v=staff.post('/api/vouchers',headers=sh,json=body)
        assert v.status_code==200,v.text
        assert reviewer.post(f'/api/vouchers/{v.json()["id"]}/decision',headers=rh,
            json={'decision':'approve'}).status_code==403
        assert owner.post('/api/fund-access',headers=oh,json={
          'user_id':ids['accountant_g2'],'fund_id':fid,'can_approve':True,
          'reason':'تفويض مستقل لاعتماد النقدية'}).status_code==200
        assert reviewer.post(f'/api/vouchers/{v.json()["id"]}/decision',headers=rh,
            json={'decision':'approve'}).status_code==200
        assert owner.post('/api/fund-access',headers=oh,json={
          'user_id':ids['worker_g2'],'fund_id':fid,'can_submit':False,
          'reason':'سحب تفويض النقدية من الموظف'}).status_code==200
        assert staff.post('/api/vouchers',headers=sh,json={**body,'description':'سند بعد السحب'}).status_code==403
        assert owner.get('/api/funds').json()[-1]['cash_restricted']==1
        print('PASS G1: cash fund restricted, independent approvals, immediate revocation')
        # Legacy fund is not unexpectedly frozen by an additive upgrade.
        funds={f['code']:f['id'] for f in owner.get('/api/funds').json()}
        ext=next(x for x in owner.get('/api/billing/config').json()['points'] if x['kind']=='external')
        assert owner.post(f'/api/billing/points/{ext["id"]}/cash-fund',headers=oh,
                          json={'fund_id':funds['cash_sub']}).status_code==200
        assert owner.post(f'/api/billing/points/{ext["id"]}/assign',headers=oh,
                          json={'user_id':ids['worker_g2']}).status_code==200
        shift=staff.post('/api/shifts/open',headers=sh,json={
          'business_date':today,'shift':'night','fund_id':funds['cash_sub']})
        assert shift.status_code==200,shift.text
        patient=staff.post('/api/billing/patients',headers=sh,json={
          'display_name':'مريض تجريبي للاستدراك','request_id':'g2_patient_key_2026'})
        assert patient.status_code==200,patient.text
        case=staff.post('/api/billing/cases',headers=sh,json={
          'patient_id':patient.json()['id'],'kind':'outpatient','point_id':ext['id'],
          'business_date':today,'request_id':'g2_case_key_2026'})
        assert case.status_code==200,case.text
        collection=staff.post(f'/api/billing/cases/{case.json()["id"]}/collect',headers=sh,json={
          'point_id':ext['id'],'parts':[{'method':'cash','amount':'500'}],
          'request_id':'g2_collect_key_2026'})
        assert collection.status_code==200,collection.text
        incident={'request_key':'g2_incident_2026_00001','point_id':ext['id'],'business_date':today,
          'shift_code':'night','incident_reason':'outage','custodian_name':'مسؤول الوردية التجريبية',
          'cash_location':'envelope','counted_cash':'500','source_register_ref':'FILE-TEST-001',
          'note':'تم استلام النقدية في ظرف مخصص أثناء تعطل التسجيل الإلكتروني'}
        assert outsider.post('/api/late-entries',headers=xh,json=incident).status_code==403
        opened=staff.post('/api/late-entries',headers=sh,json=incident)
        assert opened.status_code==200,opened.text
        inc=opened.json()['id']
        assert staff.post('/api/late-entries',headers=sh,json=incident).json()['replayed']
        assert staff.post('/api/late-entries',headers=sh,json={**incident,'note':'بيانات أخرى لا تتطابق'}).status_code==409
        assert outsider.get(f'/api/late-entries/{inc}').status_code==403
        assert outsider.get('/api/late-entries').json()['items']==[]
        item=staff.post(f'/api/late-entries/{inc}/documents',headers=sh,json={
          'paper_ref':'PAPER-REC-001','kind':'patient_receipt','method':'cash','amount':'500',
          'note':'إيصال مريض موجود أصلا إلكترونيًا'})
        assert item.status_code==200,item.text
        doc_id=item.json()['id']
        assert staff.post(f'/api/late-entries/{inc}/documents',headers=sh,json={
          'paper_ref':'PAPER-REC-001','kind':'patient_receipt','method':'cash','amount':'500'}).status_code==409
        png=b'\x89PNG\r\n\x1a\n' + b'fake-small-test-proof'
        attach=staff.post(f'/api/late-entries/{inc}/evidence',headers=sh,
            files={'file':('proof.png',png,'image/png')})
        assert attach.status_code==200,attach.text
        assert staff.post(f'/api/late-entries/{inc}/evidence',headers=sh,
            files={'file':('proof.png',png,'image/png')}).status_code==409
        assert staff.post(f'/api/late-entries/{inc}/evidence',headers=sh,
            files={'file':('proof.txt',b'unsupported-file','text/plain')}).status_code==415
        assert staff.get('/api/late-entries/evidence/'+str(attach.json()['id'])+'/download').status_code==200
        assert outsider.get('/api/late-entries/evidence/'+str(attach.json()['id'])+'/download').status_code==403
        with connect() as c:
            j_count=c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
            m_count=c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
        assert staff.post(f'/api/late-entries/{inc}/action',headers=sh,json={
           'action':'submit','note':'تم إرفاق المستندات وإرسالها للمراجعة'}).status_code==200
        # G2O: owner must explicitly grant point review before touching paper cases.
        assert owner.post(f'/api/billing/points/{ext["id"]}/assign',headers=oh,
            json={'user_id':ids['accountant_g2'],'active':True}).status_code==200
        assert reviewer.post(f'/api/late-entries/{inc}/action',headers=rh,json={
           'action':'resolve','note':'محاولة إقفال دون ربط مستندات'}).status_code==409
        assert staff.post(f'/api/late-entries/{inc}/documents/{doc_id}/link',headers=sh,json={
          'source_type':'collection','source_id':collection.json()['id'],'note':'محاولة مطابقة غير مصرح بها'}).status_code==403
        assert reviewer.post(f'/api/late-entries/{inc}/documents/{doc_id}/link',headers=rh,json={
          'source_type':'collection','source_id':9999,'note':'محاولة مطابقة ملف غير موجود'}).status_code==409
        match=reviewer.post(f'/api/late-entries/{inc}/documents/{doc_id}/link',headers=rh,json={
          'source_type':'collection','source_id':collection.json()['id'],
          'note':'مبلغ النقدية والوردية واسم النقطة متطابقان'})
        assert match.status_code==200,match.text
        assert reviewer.post(f'/api/late-entries/{inc}/documents/{doc_id}/link',headers=rh,json={
          'source_type':'collection','source_id':collection.json()['id'],
          'note':'ربط متكرر ليس مسموحًا'}).status_code==409
        resolved=reviewer.post(f'/api/late-entries/{inc}/action',headers=rh,json={
           'action':'resolve','note':'تم الربط بالتحصيل الأصلي الموجود في الحسابات ولم تدخل فلوس جديدة'})
        assert resolved.status_code==200 and resolved.json()['status']=='resolved',resolved.text
        detail=staff.get(f'/api/late-entries/{inc}')
        assert detail.status_code==200 and detail.json()['documents'][0]['linked_id']==collection.json()['id']
        # A real night collection must never reconcile a morning paper record.
        other_incident={**incident,'request_key':'g2_incident_2026_00002','shift_code':'morning',
          'source_register_ref':'FILE-TEST-002','note':'مستند صباحي مختلف عن التحصيل الليلي الموجود بالفعل'}
        shift_wrong=staff.post('/api/late-entries',headers=sh,json=other_incident)
        assert shift_wrong.status_code==200,shift_wrong.text
        morning_id=shift_wrong.json()['id']
        paper2=staff.post(f'/api/late-entries/{morning_id}/documents',headers=sh,json={
          'paper_ref':'PAPER-REC-002','kind':'patient_receipt','method':'cash','amount':'500'})
        assert paper2.status_code==200,paper2.text
        assert staff.post(f'/api/late-entries/{morning_id}/action',headers=sh,json={
          'action':'submit','note':'هذا المستند الصباحي يحتاج مطابقة مستقلة'}).status_code==200
        bad_shift=reviewer.post(f'/api/late-entries/{morning_id}/documents/{paper2.json()["id"]}/link',
          headers=rh,json={'source_type':'collection','source_id':collection.json()['id'],
                           'note':'يجب رفض المستند غير المنتمي إلى هذه الوردية'})
        assert bad_shift.status_code==409,bad_shift.text
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==j_count
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==m_count
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            for sql in ['DELETE FROM late_entry_events WHERE incident_id=?',
                        'DELETE FROM late_entry_documents WHERE incident_id=?',
                        "UPDATE late_entry_incidents SET business_date='2026-01-01' WHERE id=?"]:
                try:c.execute(sql,(inc,))
                except Exception:pass
                else:raise AssertionError('Audit origin must not mutate: '+sql)
        # Enable protection on an ALREADY USED cashier drawer without breaking
        # its active shift; after revocation an existing open session is not an escape hatch.
        assert owner.post('/api/fund-access',headers=oh,json={
          'user_id':ids['worker_g2'],'fund_id':funds['cash_sub'],'can_submit':True,
          'reason':'تفويض قبل حماية الدرج الجاري'}).status_code==200
        policy=owner.post(f'/api/funds/{funds["cash_sub"]}/access-policy',headers=oh,json={
          'restricted':True,'reason':'تفعيل تفويض صارم على الخزنة القديمة'} )
        assert policy.status_code==200,policy.text
        assert owner.post('/api/fund-access',headers=oh,json={
          'user_id':ids['worker_g2'],'fund_id':funds['cash_sub'],'can_submit':False,
          'reason':'اختبار سحب التفويض من درج ورديته مفتوحة'}).status_code==200
        denied_collection=staff.post(f'/api/billing/cases/{case.json()["id"]}/collect',headers=sh,json={
          'point_id':ext['id'],'parts':[{'method':'cash','amount':'1'}],
          'request_id':'g2_collect_after_revoked_2026'})
        assert denied_collection.status_code==403,denied_collection.text
        print('PASS G1: legacy cash opt-in lockdown applies immediately even inside an open shift')
        print('PASS G2A: late incident intake, duplicate paper guard, immutable evidence, independent source link, ZERO financial double-post')
if __name__=='__main__':run()
